"""Database queries for action_trigger. Uses explicit {schema}.table for tenant isolation."""

import psycopg
from config import DATABASE_URL, logger
from const import ACTION_PENDING
from psycopg.rows import dict_row


class DBConnection:
    """Singleton DB connection for action_trigger.

    Uses autocommit=False for transactional writes (insert execution + assign action).
    """

    _conn: psycopg.Connection | None = None

    @classmethod
    def _get_conn(cls) -> psycopg.Connection:
        if cls._conn is None or cls._conn.closed:
            logger.info("Creating new database connection")
            cls._conn = psycopg.connect(DATABASE_URL, autocommit=False, row_factory=dict_row)
        return cls._conn

    @classmethod
    def create_execution_and_assign(
        cls,
        schema_name: str,
        execution_id: str,
        command_uuid: str,
        device_id: str,
        action_id: str,
    ) -> None:
        """Insert action_execution + assign action to device in a single transaction.

        Uses ON CONFLICT DO NOTHING for idempotent SQS retries — if the execution
        already exists (from a previous attempt that failed after DB commit but before
        SNS publish), the INSERT is a no-op and the handler proceeds to publish.
        """
        conn = cls._get_conn()
        with conn.transaction():
            conn.execute(
                f"""
                INSERT INTO {schema_name}.action_executions
                    (id, device_id, action_id, command_uuid, status)
                VALUES (%(id)s, %(device_id)s, %(action_id)s, %(command_uuid)s, %(status)s)
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    "id": execution_id,
                    "device_id": device_id,
                    "action_id": action_id,
                    "command_uuid": command_uuid,
                    "status": ACTION_PENDING,
                },
            )
            conn.execute(
                f"UPDATE {schema_name}.devices SET assigned_action_id = %(action_id)s WHERE id = %(device_id)s",
                {"action_id": action_id, "device_id": device_id},
            )

    @classmethod
    def get_device_tokens(cls, schema_name: str, device_id: str) -> dict | None:
        """Get push credentials from device_tokens."""
        conn = cls._get_conn()
        return conn.execute(
            f"SELECT push_token, push_magic, topic FROM {schema_name}.device_tokens WHERE device_id = %(device_id)s",
            {"device_id": device_id},
        ).fetchone()

    @classmethod
    def get_action_details(cls, schema_name: str, action_id: str) -> dict | None:
        """Get action name, type, and configuration."""
        conn = cls._get_conn()
        return conn.execute(
            f"SELECT id, name, action_type_id, configuration FROM {schema_name}.actions WHERE id = %(action_id)s",
            {"action_id": action_id},
        ).fetchone()

    @classmethod
    def get_device_udid(cls, schema_name: str, device_id: str) -> str | None:
        """Get device UDID from device_informations."""
        conn = cls._get_conn()
        row = conn.execute(
            f"SELECT udid FROM {schema_name}.device_informations WHERE device_id = %(device_id)s",
            {"device_id": device_id},
        ).fetchone()
        return row["udid"] if row else None
