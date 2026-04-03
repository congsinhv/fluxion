"""Database queries for device_resolver. Uses explicit {schema}.table for tenant isolation."""

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
    def get_device_by_id(cls, schema_name: str, device_id: str) -> dict | None:
        """Fetch single device with full JOINs (information, tokens, state, policy)."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT
                d.id, d.state_id, d.current_policy_id, d.assigned_action_id,
                d.created_at, d.updated_at,
                s.name AS state_name,
                p.name AS policy_name, p.state_id AS policy_state_id,
                p.service_type_id AS policy_service_type_id, p.color AS policy_color,
                di.id AS info_id, di.serial_number, di.udid,
                di.name AS device_name, di.model, di.os_version,
                di.battery_level, di.wifi_mac, di.is_supervised,
                di.last_checkin_at, di.ext_fields AS info_ext_fields,
                dt.id AS token_id, dt.topic, dt.updated_at AS token_updated_at
            FROM {schema_name}.devices d
            JOIN {schema_name}.states s ON d.state_id = s.id
            LEFT JOIN {schema_name}.policies p ON d.current_policy_id = p.id
            LEFT JOIN {schema_name}.device_informations di ON d.id = di.device_id
            LEFT JOIN {schema_name}.device_tokens dt ON d.id = dt.device_id
            WHERE d.id = %(device_id)s
            """,
            {"device_id": device_id},
        ).fetchone()

    @classmethod
    def list_devices(
        cls,
        schema_name: str,
        state_id: int | None = None,
        policy_id: int | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """List devices with optional filters. Returns limit+1 rows to detect hasMore."""
        conn = cls._get_conn()

        base_sql = f"""
            SELECT
                d.id, d.state_id, d.current_policy_id, d.assigned_action_id,
                d.created_at, d.updated_at,
                s.name AS state_name,
                di.serial_number, di.name AS device_name, di.model
            FROM {schema_name}.devices d
            JOIN {schema_name}.states s ON d.state_id = s.id
            LEFT JOIN {schema_name}.device_informations di ON d.id = di.device_id
        """

        conditions: list[str] = []
        params: dict = {"limit": limit + 1, "offset": offset}

        if state_id is not None:
            conditions.append("d.state_id = %(state_id)s")
            params["state_id"] = state_id
        if policy_id is not None:
            conditions.append("d.current_policy_id = %(policy_id)s")
            params["policy_id"] = policy_id
        if search:
            conditions.append(
                "(di.serial_number ILIKE %(search)s OR di.name ILIKE %(search)s"
                " OR di.udid ILIKE %(search)s)"
            )
            params["search"] = f"%{search}%"

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"{base_sql}{where_clause} ORDER BY d.created_at DESC LIMIT %(limit)s OFFSET %(offset)s"

        return conn.execute(sql, params).fetchall()

    @classmethod
    def count_devices(
        cls,
        schema_name: str,
        state_id: int | None = None,
        policy_id: int | None = None,
        search: str | None = None,
    ) -> int:
        """Count total devices matching filters."""
        conn = cls._get_conn()

        base_sql = f"""
            SELECT COUNT(*) FROM {schema_name}.devices d
            LEFT JOIN {schema_name}.device_informations di ON d.id = di.device_id
        """

        conditions: list[str] = []
        params: dict = {}

        if state_id is not None:
            conditions.append("d.state_id = %(state_id)s")
            params["state_id"] = state_id
        if policy_id is not None:
            conditions.append("d.current_policy_id = %(policy_id)s")
            params["policy_id"] = policy_id
        if search:
            conditions.append(
                "(di.serial_number ILIKE %(search)s OR di.name ILIKE %(search)s"
                " OR di.udid ILIKE %(search)s)"
            )
            params["search"] = f"%{search}%"

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"{base_sql}{where_clause}"

        row = conn.execute(sql, params).fetchone()
        return row["count"] if row else 0

    @classmethod
    def get_device_history(
        cls, schema_name: str, device_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        """Fetch milestones for a device (history timeline). Returns (rows, total_count)."""
        conn = cls._get_conn()

        rows = conn.execute(
            f"""
            SELECT
                m.id, m.device_id, m.assigned_action_id, m.policy_id,
                m.created_at, m.ext_fields,
                a.name AS action_name, a.action_type_id,
                p.name AS policy_name, p.state_id AS policy_state_id, p.color AS policy_color
            FROM {schema_name}.milestones m
            LEFT JOIN {schema_name}.actions a ON m.assigned_action_id = a.id
            LEFT JOIN {schema_name}.policies p ON m.policy_id = p.id
            WHERE m.device_id = %(device_id)s
            ORDER BY m.created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"device_id": device_id, "limit": limit + 1, "offset": offset},
        ).fetchall()

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM {schema_name}.milestones WHERE device_id = %(device_id)s",
            {"device_id": device_id},
        ).fetchone()
        total = count_row["count"] if count_row else 0

        return rows, total

    @classmethod
    def list_available_actions(cls, schema_name: str, device_state_id: int) -> list[dict]:
        """List actions available for a device based on its current state."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT
                a.id, a.name, a.action_type_id, a.from_state_id, a.service_type_id,
                a.apply_policy_id, a.configuration,
                p.name AS policy_name, p.state_id AS policy_state_id, p.color AS policy_color
            FROM {schema_name}.actions a
            JOIN {schema_name}.policies p ON a.apply_policy_id = p.id
            WHERE a.from_state_id = %(state_id)s OR a.from_state_id IS NULL
            """,
            {"state_id": device_state_id},
        ).fetchall()
