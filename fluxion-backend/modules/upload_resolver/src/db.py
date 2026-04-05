"""Database queries for upload_resolver. Uses explicit {schema}.table for tenant isolation."""

import psycopg
from config import DATABASE_URL, logger
from psycopg.rows import dict_row


class DBConnection:
    """Singleton DB connection with tenant schema isolation via explicit schema-qualified tables."""

    _conn: psycopg.Connection | None = None

    @classmethod
    def _get_conn(cls) -> psycopg.Connection:
        if cls._conn is None or cls._conn.closed:
            logger.info("Creating new database connection")
            cls._conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
        return cls._conn

    @classmethod
    def find_existing_identifiers(
        cls, schema_name: str, serial_numbers: list[str], udids: list[str]
    ) -> list[dict]:
        """Find device_informations rows matching any of the given serial_numbers or udids."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT serial_number, udid
            FROM {schema_name}.device_informations
            WHERE serial_number = ANY(%(serials)s) OR udid = ANY(%(udids)s)
            """,
            {"serials": serial_numbers, "udids": udids},
        ).fetchall()
