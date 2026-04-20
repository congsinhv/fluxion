"""SQLAlchemy 2.0 connection wrapper with tenant schema resolution.

Tenant schema names are validated against a strict regex before interpolation
into SQL — the single safe exception to the no-f-string SQL rule
(docs/code-standards.md §5.1).
"""

from __future__ import annotations

import re
from typing import Any

from config import DATABASE_URI, logger
from exceptions import DatabaseError, TenantNotFound
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection as SAConnection
from sqlalchemy.engine import Engine, Result
from sqlalchemy.exc import SQLAlchemyError

# Schema names must match tenant_<alphanumeric+underscore> up to 40 chars.
# Validated here before interpolation to prevent SQL injection via mapping table.
_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


class Connection:
    """SQLAlchemy connection wrapper with tenant schema lookup and safe execution.

    Instantiate once per Lambda invocation, call close() in a finally block.

    Args:
        database_uri: SQLAlchemy-compatible connection URL. Defaults to the
            DATABASE_URI env var loaded from config.

    Raises:
        DatabaseError: If the initial connection attempt fails.
    """

    def __init__(self, database_uri: str = DATABASE_URI) -> None:
        try:
            self._engine: Engine = create_engine(database_uri)
            self._connection: SAConnection = self._engine.connect()
        except SQLAlchemyError as e:
            logger.exception("db.connect_failed")
            raise DatabaseError("database connection failed") from e

    def get_schema_name(self, tenant_id: str) -> str:
        """Resolve tenant_id to a validated schema name via the mapping table.

        Args:
            tenant_id: UUID string of the tenant.

        Returns:
            Schema name string, e.g. ``tenant_acme``.

        Raises:
            DatabaseError: Lookup failed or schema name fails validation.
            TenantNotFound: No row found for tenant_id.
        """
        query = text("""
            SELECT tsm.schema_name
            FROM public.t_tenant_schema_mapping tsm
            WHERE tsm.tenant_id = :tenant_id
        """)
        try:
            row = self._execute(query, {"tenant_id": tenant_id}).fetchone()
        except SQLAlchemyError as e:
            logger.exception("db.get_schema_name_failed", extra={"tenant_id": tenant_id})
            raise DatabaseError("tenant lookup failed") from e
        if not row:
            raise TenantNotFound(tenant_id)
        schema_name: str = row.schema_name
        if not _SCHEMA_NAME_RE.fullmatch(schema_name):
            raise DatabaseError(f"invalid schema_name in mapping: {schema_name!r}")
        return schema_name

    def _execute(self, query: Any, params: dict[str, Any] | None = None) -> Result[Any]:
        """Execute a parameterised SQLAlchemy text query.

        Args:
            query: A ``sqlalchemy.text()`` object.
            params: Named parameter dict (``{":name": value}`` style).

        Returns:
            SQLAlchemy Result object.
        """
        return self._connection.execute(query, params or {})

    def close(self) -> None:
        """Close the underlying connection and dispose the engine pool."""
        self._connection.close()
        self._engine.dispose()
