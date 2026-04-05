"""Database queries for upload_processor. Uses explicit {schema}.table for tenant isolation."""

import psycopg
from config import DATABASE_URL, logger
from const import INITIAL_POLICY_ID, INITIAL_STATE_ID
from psycopg.rows import dict_row


class DBConnection:
    """Singleton DB connection for upload_processor.

    Uses autocommit=False for explicit transaction control — device + device_information
    must be inserted atomically to avoid orphan rows.
    """

    _conn: psycopg.Connection | None = None

    @classmethod
    def _get_conn(cls) -> psycopg.Connection:
        if cls._conn is None or cls._conn.closed:
            logger.info("Creating new database connection")
            cls._conn = psycopg.connect(DATABASE_URL, autocommit=False, row_factory=dict_row)
        return cls._conn

    @classmethod
    def insert_device_with_info(
        cls,
        schema_name: str,
        serial_number: str,
        udid: str,
        name: str | None,
        model: str | None,
        os_version: str | None,
    ) -> str | None:
        """Insert device + device_information in a single transaction.

        Returns device_id (str) if inserted, None if serial/udid conflict.
        Uses ON CONFLICT DO NOTHING on device_informations to handle duplicates.
        Transaction ensures no orphan device rows on conflict.
        """
        conn = cls._get_conn()
        with conn.transaction():
            # Try inserting device_information first to detect conflicts early
            info_row = conn.execute(
                f"""
                INSERT INTO {schema_name}.device_informations
                    (serial_number, udid, name, model, os_version)
                VALUES (%(serial)s, %(udid)s, %(name)s, %(model)s, %(os_version)s)
                ON CONFLICT (serial_number) DO NOTHING
                RETURNING id
                """,
                {
                    "serial": serial_number,
                    "udid": udid,
                    "name": name,
                    "model": model,
                    "os_version": os_version,
                },
            ).fetchone()

            if info_row is None:
                # Conflict — serial already exists, skip device insert
                return None

            # No conflict — insert device and link via device_id
            device_row = conn.execute(
                f"""
                INSERT INTO {schema_name}.devices (state_id, current_policy_id)
                VALUES (%(state_id)s, %(policy_id)s)
                RETURNING id
                """,
                {"state_id": INITIAL_STATE_ID, "policy_id": INITIAL_POLICY_ID},
            ).fetchone()
            device_id = str(device_row["id"])

            # Link device_information to device
            conn.execute(
                f"""
                UPDATE {schema_name}.device_informations
                SET device_id = %(device_id)s
                WHERE id = %(info_id)s
                """,
                {"device_id": device_id, "info_id": str(info_row["id"])},
            )

            return device_id
