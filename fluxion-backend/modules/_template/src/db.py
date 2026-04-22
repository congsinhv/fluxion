"""psycopg3 connection wrapper with tenant schema lookup and permission check.

Usage pattern per request (context manager):

    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        allowed = db.has_permission(ctx.cognito_sub, ctx.tenant_id, "device:read")

See design-patterns.md §5 (Repository Pattern) and §11 (Tenant-per-Schema).
"""

from __future__ import annotations

import re
from typing import Any

import psycopg
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, TenantNotFoundError

# Matches accesscontrol.tenants.ck_tenants_schema_name_format.
# Bare names only: dev1, acme, fpt (no prefix). See design-patterns.md §11.2.
_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _validate_schema(schema_name: str) -> str:
    """Raise DatabaseError if schema_name fails the safety regex.

    Args:
        schema_name: Candidate schema name to validate.

    Returns:
        The validated schema_name, unchanged.

    Raises:
        DatabaseError: Name does not match ``^[a-z][a-z0-9_]{0,39}$``.
    """
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


class Database:
    """psycopg3 connection bound to a single Lambda invocation.

    Opens one synchronous connection at construction; closes it in __exit__.
    All schema-qualified SQL uses ``psycopg.sql.Identifier`` — never f-string
    for schema names (defense-in-depth against tenant-schema injection).

    Args:
        dsn: PostgreSQL DSN (``DATABASE_URI`` env var in production).
        tenant_schema: Validated tenant schema name (from auth context).

    Raises:
        DatabaseError: If the initial connection fails.
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
    # accesscontrol helpers
    # ------------------------------------------------------------------

    def get_schema_name(self, tenant_id: int) -> str:
        """Resolve tenant BIGINT id to a validated schema name.

        Args:
            tenant_id: The tenant id from the Cognito auth claim.

        Returns:
            Validated schema name (e.g. ``"dev1"``).

        Raises:
            TenantNotFoundError: No row exists for tenant_id.
            DatabaseError: Query failed or schema name fails regex.
        """
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
        """Check whether a user holds a permission, optionally scoped to tenant.

        Joins accesscontrol.users → users_permissions → permissions.
        A NULL tenant_id on the grant row means a global (super-admin) grant.

        Args:
            cognito_sub: User's Cognito subject claim (from event.identity.claims.sub).
            tenant_id: Tenant BIGINT id (from Cognito custom claim).
            code: Permission code to check (e.g. ``"device:read"``).

        Returns:
            True if the user holds the permission for the tenant (or globally).

        Raises:
            DatabaseError: Query execution failed.
        """
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
    # Internal
    # ------------------------------------------------------------------

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
