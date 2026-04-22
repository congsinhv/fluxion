"""psycopg3 repository for user_resolver.

All SQL against accesscontrol.users (shared schema, not per-tenant).
Real table columns (from migration 7124824094ea):
  accesscontrol.users — id BIGINT, email TEXT, cognito_sub TEXT, name TEXT,
                        enabled BOOLEAN, created_at TIMESTAMPTZ

No tenant_id column exists on users — permissions are in users_permissions.
role lives in Cognito custom:role; callers must enrich via cognito.admin_get_user.

Pagination (listUsers):
  - Cursor = base64-encoded last-seen id (opaque to callers).
  - WHERE id > cursor_id ORDER BY id LIMIT n.
  - Returns nextToken=None when fewer rows than limit returned.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import psycopg
import psycopg.rows
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, InvalidInputError, NotFoundError, TenantNotFoundError

_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

# Map UpdateUserInput camelCase field names → DB snake_case column names.
# role is Cognito-only in v1 — excluded from DB update map.
_USER_COL_MAP: dict[str, str] = {
    "name": "name",
    "isActive": "enabled",
}


def _validate_schema(schema_name: str) -> str:
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


def _encode_cursor(user_id: int) -> str:
    """Encode user id into an opaque base64 pagination token."""
    return base64.urlsafe_b64encode(str(user_id).encode()).decode()


def _decode_cursor(token: str) -> int:
    """Decode pagination token back to user id.

    Raises:
        InvalidInputError: Token is malformed.
    """
    try:
        return int(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception as exc:
        raise InvalidInputError(f"invalid nextToken: {token!r}") from exc


class Database:
    """psycopg3 connection bound to a single Lambda invocation.

    Context-manager only — do not use outside ``with Database(...) as db:``.
    tenant_schema is accepted for compatibility with auth.py helpers but
    user CRUD operates on the shared accesscontrol schema directly.
    """

    def __init__(self, dsn: str = DATABASE_URI, tenant_schema: str = "") -> None:
        self._dsn = dsn
        self._tenant_schema = _validate_schema(tenant_schema) if tenant_schema else ""
        self._conn: psycopg.Connection[Any] | None = None

    def __enter__(self) -> Database:
        try:
            self._conn = psycopg.connect(self._dsn, row_factory=psycopg.rows.dict_row)
        except psycopg.Error as exc:
            logger.exception("db.connect_failed")
            raise DatabaseError("database connection failed") from exc
        return self

    def __exit__(self, *_: object) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg.Error:
                logger.warning("db.close_failed")
            finally:
                self._conn = None

    # ------------------------------------------------------------------
    # accesscontrol helpers (shared with auth.py)
    # ------------------------------------------------------------------

    def get_schema_name(self, tenant_id: int) -> str:
        """Resolve tenant BIGINT id → validated schema name."""
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT schema_name FROM accesscontrol.tenants WHERE id = %s",
                    (tenant_id,),
                )
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.get_schema_name_failed", extra={"tenant_id": tenant_id})
            raise DatabaseError("tenant lookup failed") from exc
        if not row:
            raise TenantNotFoundError(str(tenant_id))
        return _validate_schema(str(row["schema_name"]))

    def has_permission(self, cognito_sub: str, tenant_id: int, code: str) -> bool:
        """Return True if user holds permission code for the tenant (or globally)."""
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM accesscontrol.users u
                    JOIN accesscontrol.users_permissions up ON u.id = up.user_id
                    JOIN accesscontrol.permissions p       ON p.id = up.permission_id
                    WHERE u.cognito_sub = %s
                      AND p.code = %s
                      AND (up.tenant_id = %s OR up.tenant_id IS NULL)
                    LIMIT 1
                    """,
                    (cognito_sub, code, tenant_id),
                )
                return cur.fetchone() is not None
        except psycopg.Error as exc:
            logger.exception(
                "db.has_permission_failed",
                extra={"cognito_sub": cognito_sub, "code": code},
            )
            raise DatabaseError("permission check failed") from exc

    # ------------------------------------------------------------------
    # User reads
    # ------------------------------------------------------------------

    def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        """Fetch a single user row by BIGINT id.

        Raises:
            NotFoundError: No row with that id.
            DatabaseError: Query failed.
        """
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, cognito_sub, name, enabled, created_at "
                    "FROM accesscontrol.users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.get_user_by_id_failed", extra={"user_id": user_id})
            raise DatabaseError("get_user_by_id query failed") from exc
        if not row:
            raise NotFoundError(f"user id={user_id}")
        return dict(row)

    def get_user_by_cognito_sub(self, cognito_sub: str) -> dict[str, Any]:
        """Fetch a single user row by Cognito sub (for getCurrentUser).

        Raises:
            NotFoundError: No row with that cognito_sub.
            DatabaseError: Query failed.
        """
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, cognito_sub, name, enabled, created_at "
                    "FROM accesscontrol.users WHERE cognito_sub = %s",
                    (cognito_sub,),
                )
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.get_user_by_cognito_sub_failed")
            raise DatabaseError("get_user_by_cognito_sub query failed") from exc
        if not row:
            raise NotFoundError(f"user cognito_sub={cognito_sub!r}")
        return dict(row)

    def list_users(
        self,
        limit: int = 20,
        after_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` user rows ordered by id, optionally after ``after_id``.

        Args:
            limit:    Maximum rows to return (1–100).
            after_id: Exclusive lower bound on id (cursor-based pagination).

        Returns:
            List of row dicts; may be shorter than limit when exhausted.
        """
        conn = self._require_conn()
        if after_id is not None:
            query = psycopg.sql.SQL(
                "SELECT id, email, cognito_sub, name, enabled, created_at "
                "FROM accesscontrol.users WHERE id > %s ORDER BY id LIMIT %s"
            )
            params: list[Any] = [after_id, limit]
        else:
            query = psycopg.sql.SQL(
                "SELECT id, email, cognito_sub, name, enabled, created_at "
                "FROM accesscontrol.users ORDER BY id LIMIT %s"
            )
            params = [limit]
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_users_failed")
            raise DatabaseError("list_users query failed") from exc

    # ------------------------------------------------------------------
    # User writes (createUser flow)
    # ------------------------------------------------------------------

    def create_user_placeholder(self, email: str, name: str) -> int:
        """INSERT user row with cognito_sub=NULL; return new BIGINT id.

        This is step 1 of the createUser flow. cognito_sub is filled in by
        set_user_cognito_sub after Cognito user creation succeeds.

        Raises:
            InvalidInputError: email already exists (UNIQUE constraint).
            DatabaseError:     Other insert failure.
        """
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO accesscontrol.users (email, name) VALUES (%s, %s) RETURNING id",
                    (email, name),
                )
                row = cur.fetchone()
                conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            conn.rollback()
            raise InvalidInputError(f"email already exists: {email!r}") from exc
        except psycopg.Error as exc:
            conn.rollback()
            logger.exception("db.create_user_placeholder_failed", extra={"email": email})
            raise DatabaseError("create_user_placeholder failed") from exc
        if not row:
            raise DatabaseError("create_user_placeholder: no row returned")
        return int(row["id"])

    def set_user_cognito_sub(self, user_id: int, sub: str) -> None:
        """UPDATE cognito_sub on the placeholder row created in step 1.

        Args:
            user_id: BIGINT id of the placeholder row.
            sub:     Cognito sub UUID returned by admin_create_user.

        Raises:
            NotFoundError: Row was deleted between steps (race condition).
            DatabaseError: Update failed.
        """
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE accesscontrol.users SET cognito_sub = %s WHERE id = %s RETURNING id",
                    (sub, user_id),
                )
                row = cur.fetchone()
                conn.commit()
        except psycopg.Error as exc:
            conn.rollback()
            logger.exception("db.set_user_cognito_sub_failed", extra={"user_id": user_id})
            raise DatabaseError("set_user_cognito_sub failed") from exc
        if not row:
            raise NotFoundError(f"user id={user_id} vanished before sub update")

    def delete_user(self, user_id: int) -> None:
        """DELETE user row — rollback helper only (called on Cognito failure).

        Silently succeeds if the row no longer exists.

        Raises:
            DatabaseError: Delete failed for an unexpected reason.
        """
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM accesscontrol.users WHERE id = %s",
                    (user_id,),
                )
                conn.commit()
        except psycopg.Error as exc:
            conn.rollback()
            logger.exception("db.delete_user_failed", extra={"user_id": user_id})
            raise DatabaseError("delete_user failed") from exc

    def update_user(self, user_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        """PATCH user row with the provided fields (exclude_unset from Pydantic).

        Supported keys (camelCase from UpdateUserInput, excluding role which is
        Cognito-only in v1): name, isActive.

        Args:
            user_id: BIGINT id of the user to update.
            fields:  Dict of camelCase field names → values (exclude_unset).

        Raises:
            InvalidInputError: No recognised DB fields in patch.
            NotFoundError:     Row does not exist.
            DatabaseError:     Query failed.
        """
        db_fields = {_USER_COL_MAP[k]: v for k, v in fields.items() if k in _USER_COL_MAP}
        if not db_fields:
            raise InvalidInputError("updateUser: no DB-writable fields provided")

        conn = self._require_conn()
        set_clauses = psycopg.sql.SQL(", ").join(
            psycopg.sql.SQL("{col} = %s").format(col=psycopg.sql.Identifier(col))
            for col in db_fields
        )
        params: list[Any] = list(db_fields.values())
        params.append(user_id)

        query = psycopg.sql.SQL(
            "UPDATE accesscontrol.users SET {set} WHERE id = %s "
            "RETURNING id, email, cognito_sub, name, enabled, created_at"
        ).format(set=set_clauses)

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                conn.commit()
        except psycopg.Error as exc:
            conn.rollback()
            logger.exception("db.update_user_failed", extra={"user_id": user_id})
            raise DatabaseError("update_user failed") from exc

        if not row:
            raise NotFoundError(f"user id={user_id}")
        return dict(row)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
