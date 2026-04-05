"""Database queries for checkin_handler. Uses explicit {schema}.table for tenant isolation."""

import psycopg
from config import DATABASE_URL, logger
from psycopg.rows import dict_row

# Sentinel for "don't update this column" in update_device
_SKIP = object()


class DBConnection:
    """Singleton DB connection for checkin_handler.

    4 generic functions covering all event types:
    - update_device_token: UPSERT device_tokens
    - update_device: UPDATE devices with dynamic SET clauses
    - update_action_execution: UPDATE action_executions by command_uuid
    - insert_milestone: INSERT milestones
    """

    _conn: psycopg.Connection | None = None

    @classmethod
    def _get_conn(cls) -> psycopg.Connection:
        if cls._conn is None or cls._conn.closed:
            logger.info("Creating new database connection")
            cls._conn = psycopg.connect(DATABASE_URL, autocommit=False, row_factory=dict_row)
        return cls._conn

    @classmethod
    def update_device_token(
        cls,
        schema_name: str,
        device_id: str,
        push_token: bytes | None,
        push_magic: str | None,
        topic: str | None,
        unlock_token: bytes | None,
    ) -> None:
        """UPSERT device_tokens — ON CONFLICT (device_id) DO UPDATE."""
        conn = cls._get_conn()
        with conn.transaction():
            conn.execute(
                f"""
                INSERT INTO {schema_name}.device_tokens (device_id, push_token, push_magic, topic, unlock_token)
                VALUES (%(device_id)s, %(push_token)s, %(push_magic)s, %(topic)s, %(unlock_token)s)
                ON CONFLICT (device_id) DO UPDATE SET
                    push_token = EXCLUDED.push_token,
                    push_magic = EXCLUDED.push_magic,
                    topic = EXCLUDED.topic,
                    unlock_token = EXCLUDED.unlock_token,
                    updated_at = NOW()
                """,
                {
                    "device_id": device_id,
                    "push_token": push_token,
                    "push_magic": push_magic,
                    "topic": topic,
                    "unlock_token": unlock_token,
                },
            )

    @classmethod
    def update_device(
        cls,
        schema_name: str,
        device_id: str,
        state_id: int | None = None,
        current_policy_id: int | None = None,
        assigned_action_id=_SKIP,
    ) -> None:
        """UPDATE devices with dynamic SET clauses.

        Pass assigned_action_id=None to clear it, _SKIP (default) to leave unchanged.
        """
        conn = cls._get_conn()
        sets: list[str] = []
        params: dict = {"device_id": device_id}

        if state_id is not None:
            sets.append("state_id = %(state_id)s")
            params["state_id"] = state_id
        if current_policy_id is not None:
            sets.append("current_policy_id = %(policy_id)s")
            params["policy_id"] = current_policy_id
        if assigned_action_id is not _SKIP:
            sets.append("assigned_action_id = %(action_id)s")
            params["action_id"] = assigned_action_id

        if not sets:
            return

        with conn.transaction():
            conn.execute(
                f"UPDATE {schema_name}.devices SET {', '.join(sets)} WHERE id = %(device_id)s",
                params,
            )

    @classmethod
    def update_action_execution(
        cls, schema_name: str, command_uuid: str, status: str
    ) -> dict | None:
        """UPDATE action_executions by command_uuid. Returns execution row."""
        conn = cls._get_conn()
        with conn.transaction():
            return conn.execute(
                f"""
                UPDATE {schema_name}.action_executions
                SET status = %(status)s
                WHERE command_uuid = %(command_uuid)s
                RETURNING id, device_id, action_id
                """,
                {"status": status, "command_uuid": command_uuid},
            ).fetchone()

    @classmethod
    def insert_milestone(
        cls, schema_name: str, device_id: str, action_id: str, policy_id: int
    ) -> None:
        """INSERT milestones row for device history timeline."""
        conn = cls._get_conn()
        with conn.transaction():
            conn.execute(
                f"""
                INSERT INTO {schema_name}.milestones (device_id, assigned_action_id, policy_id)
                VALUES (%(device_id)s, %(action_id)s, %(policy_id)s)
                """,
                {"device_id": device_id, "action_id": action_id, "policy_id": policy_id},
            )

    @classmethod
    def get_action_policy(cls, schema_name: str, action_id: str) -> dict | None:
        """Get action's apply_policy with state_id. Returns {apply_policy_id, state_id}."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT a.apply_policy_id, p.state_id
            FROM {schema_name}.actions a
            JOIN {schema_name}.policies p ON a.apply_policy_id = p.id
            WHERE a.id = %(action_id)s
            """,
            {"action_id": action_id},
        ).fetchone()
