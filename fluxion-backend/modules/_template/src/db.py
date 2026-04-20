"""SQLAlchemy connection wrapper with tenant schema lookup.

Usage pattern per request:

    conn = Connection()
    try:
        schema = conn.get_schema_name(tenant_id)
        # Pass schema into tenant-scoped repository classes built on conn.
    finally:
        conn.close()

See design-patterns.md §5 (Repository Pattern) and §11 (Tenant-per-Schema).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from config import DATABASE_URI, logger
from exceptions import DatabaseError, TenantNotFoundError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection as SAConnection
    from sqlalchemy.engine import Engine, Result

# Regex guards against SQL injection via schema interpolation.
# Only values matching this pattern may be f-string-interpolated into queries.
# See design-patterns.md §11.2.
_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


class Connection:
    """SQLAlchemy connection wrapper with tenant schema lookup and safe execute.

    Wraps a single SQLAlchemy connection for the lifetime of one Lambda
    invocation. Resolves tenant_id → schema_name via
    ``public.t_tenant_schema_mapping`` and regex-validates the result before
    any schema-qualified query may use it.

    Raises:
        DatabaseError: If the initial connection to PostgreSQL fails.
    """

    def __init__(self) -> None:
        try:
            self._engine: Engine = create_engine(DATABASE_URI)
            self._connection: SAConnection = self._engine.connect()
        except SQLAlchemyError as exc:
            logger.exception("db.connect_failed")
            raise DatabaseError("database connection failed") from exc

    def get_schema_name(self, tenant_id: str) -> str:
        """Resolve tenant_id to a validated schema name.

        Queries ``public.t_tenant_schema_mapping`` and validates the returned
        schema name against ``^tenant_[a-z0-9_]{1,40}$`` before returning.
        The validated value is safe for f-string interpolation into SQL.

        Args:
            tenant_id: The tenant UUID from the Cognito auth claim.

        Returns:
            Validated schema name (e.g. ``"tenant_acme"``).

        Raises:
            TenantNotFoundError: No mapping row exists for tenant_id.
            DatabaseError: Query failed or schema name failed regex validation.
        """
        query = text(
            """
            SELECT tsm.schema_name
            FROM public.t_tenant_schema_mapping tsm
            WHERE tsm.tenant_id = :tenant_id
            """
        )
        try:
            row = self._execute(query, {"tenant_id": tenant_id}).fetchone()
        except SQLAlchemyError as exc:
            logger.exception("db.get_schema_name_failed", extra={"tenant_id": tenant_id})
            raise DatabaseError("tenant lookup failed") from exc

        if not row:
            raise TenantNotFoundError(tenant_id)

        # SQLAlchemy Row attribute access returns Any; cast explicitly so mypy
        # can verify downstream usage as str.
        schema_name: str = str(row._mapping["schema_name"])  # noqa: SLF001
        if not _SCHEMA_NAME_RE.fullmatch(schema_name):
            raise DatabaseError(f"invalid schema_name in mapping: {schema_name!r}")
        return schema_name

    def _execute(self, query: Any, params: dict[str, Any] | None = None) -> Result:
        """Execute a SQLAlchemy text() query with named parameters.

        Args:
            query: A ``sqlalchemy.text()`` expression.
            params: Named parameter dict (``{":name": value}`` style).

        Returns:
            SQLAlchemy Result object.
        """
        return self._connection.execute(query, params or {})

    def close(self) -> None:
        """Close the connection and dispose of the engine connection pool."""
        self._connection.close()
        self._engine.dispose()
