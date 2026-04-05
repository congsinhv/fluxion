"""Database queries for platform_resolver. Uses explicit {schema}.table for tenant isolation."""

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

    # ─── Read queries ────────────────────────────────────────────────────────────

    @classmethod
    def list_states(cls, schema_name: str) -> list[dict]:
        conn = cls._get_conn()
        return conn.execute(f"SELECT id, name FROM {schema_name}.states ORDER BY id").fetchall()

    @classmethod
    def list_policies(cls, schema_name: str, service_type_id: int | None = None) -> list[dict]:
        conn = cls._get_conn()
        sql = f"""
            SELECT p.id, p.name, p.state_id, p.service_type_id, p.color,
                   st.name AS state_name
            FROM {schema_name}.policies p
            JOIN {schema_name}.states st ON p.state_id = st.id
        """
        params: dict = {}
        if service_type_id is not None:
            sql += " WHERE p.service_type_id = %(service_type_id)s"
            params["service_type_id"] = service_type_id
        sql += " ORDER BY p.id"
        return conn.execute(sql, params).fetchall()

    @classmethod
    def list_actions(
        cls,
        schema_name: str,
        from_state_id: int | None = None,
        service_type_id: int | None = None,
    ) -> list[dict]:
        conn = cls._get_conn()
        sql = f"""
            SELECT a.id, a.name, a.action_type_id, a.from_state_id,
                   a.service_type_id, a.apply_policy_id, a.configuration,
                   p.name AS policy_name,
                   p.state_id AS policy_state_id, p.color AS policy_color
            FROM {schema_name}.actions a
            JOIN {schema_name}.policies p ON a.apply_policy_id = p.id
        """
        conditions: list[str] = []
        params: dict = {}
        if from_state_id is not None:
            conditions.append("a.from_state_id = %(from_state_id)s")
            params["from_state_id"] = from_state_id
        if service_type_id is not None:
            conditions.append("a.service_type_id = %(service_type_id)s")
            params["service_type_id"] = service_type_id
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY a.name"
        return conn.execute(sql, params).fetchall()

    @classmethod
    def list_services(cls, schema_name: str) -> list[dict]:
        conn = cls._get_conn()
        return conn.execute(
            f"SELECT id, name, is_enabled FROM {schema_name}.services ORDER BY id"
        ).fetchall()

    # ─── Update mutations ────────────────────────────────────────────────────────

    @classmethod
    def update_state(cls, schema_name: str, state_id: int, name: str) -> dict | None:
        conn = cls._get_conn()
        return conn.execute(
            f"UPDATE {schema_name}.states SET name = %(name)s WHERE id = %(id)s RETURNING id, name",
            {"name": name, "id": state_id},
        ).fetchone()

    @classmethod
    def update_policy(cls, schema_name: str, policy_id: int, input_data: dict) -> dict | None:
        conn = cls._get_conn()
        return conn.execute(
            f"""
            UPDATE {schema_name}.policies SET
                name = COALESCE(%(name)s, name),
                state_id = COALESCE(%(state_id)s, state_id),
                service_type_id = COALESCE(%(service_type_id)s, service_type_id),
                color = COALESCE(%(color)s, color)
            WHERE id = %(id)s
            RETURNING id, name, state_id, service_type_id, color
            """,
            {
                "name": input_data.get("name"),
                "state_id": input_data.get("stateId"),
                "service_type_id": input_data.get("serviceTypeId"),
                "color": input_data.get("color"),
                "id": policy_id,
            },
        ).fetchone()

    @classmethod
    def update_action(cls, schema_name: str, action_id: str, input_data: dict) -> dict | None:
        conn = cls._get_conn()
        return conn.execute(
            f"""
            UPDATE {schema_name}.actions SET
                name = COALESCE(%(name)s, name),
                action_type_id = COALESCE(%(action_type_id)s, action_type_id),
                from_state_id = COALESCE(%(from_state_id)s, from_state_id),
                service_type_id = COALESCE(%(service_type_id)s, service_type_id),
                apply_policy_id = COALESCE(%(apply_policy_id)s, apply_policy_id),
                configuration = COALESCE(%(configuration)s, configuration)
            WHERE id = %(id)s
            RETURNING id, name, action_type_id, from_state_id,
                      service_type_id, apply_policy_id, configuration
            """,
            {
                "name": input_data.get("name"),
                "action_type_id": input_data.get("actionTypeId"),
                "from_state_id": input_data.get("fromStateId"),
                "service_type_id": input_data.get("serviceTypeId"),
                "apply_policy_id": input_data.get("applyPolicyId"),
                "configuration": input_data.get("configuration"),
                "id": action_id,
            },
        ).fetchone()

    @classmethod
    def update_service(cls, schema_name: str, service_id: int, input_data: dict) -> dict | None:
        conn = cls._get_conn()
        return conn.execute(
            f"""
            UPDATE {schema_name}.services SET
                name = COALESCE(%(name)s, name),
                is_enabled = COALESCE(%(is_enabled)s, is_enabled)
            WHERE id = %(id)s
            RETURNING id, name, is_enabled
            """,
            {"name": input_data.get("name"), "is_enabled": input_data.get("isEnabled"), "id": service_id},
        ).fetchone()
