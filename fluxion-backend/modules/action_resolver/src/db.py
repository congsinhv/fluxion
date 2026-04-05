"""Database queries for action_resolver. Uses explicit {schema}.table for tenant isolation."""

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
    def get_device_for_action(cls, schema_name: str, device_id: str) -> dict | None:
        """Fetch device id, state_id, assigned_action_id for FSM validation."""
        conn = cls._get_conn()
        return conn.execute(
            f"SELECT id, state_id, assigned_action_id FROM {schema_name}.devices WHERE id = %(device_id)s",
            {"device_id": device_id},
        ).fetchone()

    @classmethod
    def get_action_by_id(cls, schema_name: str, action_id: str) -> dict | None:
        """Fetch action for FSM guard validation."""
        conn = cls._get_conn()
        return conn.execute(
            f"SELECT id, name, from_state_id, configuration FROM {schema_name}.actions WHERE id = %(action_id)s",
            {"action_id": action_id},
        ).fetchone()
