"""Database queries for user_resolver. Uses explicit {schema}.table for tenant isolation."""

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
    def get_user_by_id(cls, schema_name: str, user_id: str) -> dict | None:
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT id, email, name, role, is_active, cognito_sub, created_at, updated_at
            FROM {schema_name}.users WHERE id = %(user_id)s
            """,
            {"user_id": user_id},
        ).fetchone()

    @classmethod
    def get_user_by_cognito_sub(cls, schema_name: str, cognito_sub: str) -> dict | None:
        """Fetch user by Cognito sub claim (for `me` query)."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT id, email, name, role, is_active, cognito_sub, created_at, updated_at
            FROM {schema_name}.users WHERE cognito_sub = %(cognito_sub)s
            """,
            {"cognito_sub": cognito_sub},
        ).fetchone()

    @classmethod
    def list_users(cls, schema_name: str, limit: int = 20, offset: int = 0) -> list[dict]:
        """List users with pagination. Returns limit+1 rows to detect hasMore."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            SELECT id, email, name, role, is_active, created_at, updated_at
            FROM {schema_name}.users ORDER BY created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"limit": limit + 1, "offset": offset},
        ).fetchall()

    @classmethod
    def count_users(cls, schema_name: str) -> int:
        conn = cls._get_conn()
        row = conn.execute(f"SELECT COUNT(*) FROM {schema_name}.users").fetchone()
        return row["count"] if row else 0

    @classmethod
    def create_user(
        cls, schema_name: str, email: str, name: str, role: str, cognito_sub: str
    ) -> dict | None:
        """Insert new user record. Caller must create Cognito user first."""
        conn = cls._get_conn()
        return conn.execute(
            f"""
            INSERT INTO {schema_name}.users (email, name, role, cognito_sub)
            VALUES (%(email)s, %(name)s, %(role)s, %(cognito_sub)s)
            RETURNING id, email, name, role, is_active, created_at, updated_at
            """,
            {"email": email, "name": name, "role": role.lower(), "cognito_sub": cognito_sub},
        ).fetchone()

    @classmethod
    def update_user(cls, schema_name: str, user_id: str, input_data: dict) -> dict | None:
        conn = cls._get_conn()
        role = input_data.get("role")
        return conn.execute(
            f"""
            UPDATE {schema_name}.users SET
                name = COALESCE(%(name)s, name),
                role = COALESCE(%(role)s, role),
                is_active = COALESCE(%(is_active)s, is_active),
                updated_at = NOW()
            WHERE id = %(user_id)s
            RETURNING id, email, name, role, is_active, cognito_sub, created_at, updated_at
            """,
            {
                "name": input_data.get("name"),
                "role": role.lower() if role else None,
                "is_active": input_data.get("isActive"),
                "user_id": user_id,
            },
        ).fetchone()
