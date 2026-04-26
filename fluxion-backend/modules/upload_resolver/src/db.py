"""psycopg3 repository for upload_resolver.

Tenant-isolated: every SQL query uses psycopg.sql.Identifier for schema names.
Never use f-string interpolation for schema names (SQL injection defense).

Tables used:
  accesscontrol.tenants        — id BIGINT, schema_name TEXT
  accesscontrol.users          — id BIGINT, cognito_sub TEXT
  accesscontrol.users_permissions — user_id, permission_id, tenant_id
  accesscontrol.permissions    — id, code TEXT

  Per-tenant schema:
  device_informations          — serial_number TEXT UNIQUE, udid TEXT UNIQUE
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

import psycopg
import psycopg.rows
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, TenantNotFoundError

# Matches accesscontrol.tenants.ck_tenants_schema_name_format.
_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _validate_schema(schema_name: str) -> str:
    """Raise DatabaseError if schema_name fails the safety regex."""
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


class ExistingDeviceKeys(NamedTuple):
    """Sets of serial_numbers and udids that already exist in the tenant schema."""

    serials: set[str]
    udids: set[str]


class Database:
    """psycopg3 connection bound to a single Lambda invocation.

    Context-manager only — do not use outside ``with Database() as db:``.
    All schema-qualified SQL uses ``psycopg.sql.Identifier`` — never f-string.

    Raises:
        DatabaseError: If the initial connection fails.
    """

    def __init__(self) -> None:
        self._conn: psycopg.Connection[Any] | None = None

    def __enter__(self) -> Database:
        try:
            self._conn = psycopg.connect(DATABASE_URI, row_factory=psycopg.rows.dict_row)
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
        """Resolve tenant BIGINT id → validated schema name.

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
        """Return True if user holds permission code for the tenant (or globally).

        Args:
            cognito_sub: User's Cognito subject claim.
            tenant_id:   Tenant BIGINT id.
            code:        Permission code (e.g. ``"upload:write"``).

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
    # Upload-resolver repo methods
    # ------------------------------------------------------------------

    def find_existing_device_keys(
        self,
        serials: list[str],
        udids: list[str],
        schema: str,
    ) -> ExistingDeviceKeys:
        """Return serial_numbers and udids that already exist in the tenant schema.

        Uses a single ``WHERE serial_number = ANY(...) OR udid = ANY(...)`` query.
        Both columns are UNIQUE-indexed so this is cheap.

        Args:
            serials: List of serial_number strings to check.
            udids:   List of udid strings to check.
            schema:  Validated tenant schema name.

        Returns:
            ``ExistingDeviceKeys(serials=set, udids=set)`` — sets of already-existing
            values. Either set may be empty if none of the given values conflict.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()

        # Empty inputs: skip query and return empty sets (nothing can conflict).
        if not serials and not udids:
            return ExistingDeviceKeys(serials=set(), udids=set())

        # Normalize to non-empty lists for ANY() parameterization.
        # psycopg requires at least one element per array literal.
        safe_serials = serials if serials else ["__no_match__"]
        safe_udids = udids if udids else ["__no_match__"]

        query = psycopg.sql.SQL(
            """
            SELECT serial_number, udid
            FROM   {schema}.device_informations
            WHERE  serial_number = ANY(%s)
               OR  udid = ANY(%s)
            """
        ).format(schema=psycopg.sql.Identifier(schema))

        try:
            with conn.cursor() as cur:
                cur.execute(query, (safe_serials, safe_udids))
                rows = cur.fetchall()
        except psycopg.Error as exc:
            logger.exception(
                "db.find_existing_device_keys_failed",
                extra={"schema": schema, "serial_count": len(serials), "udid_count": len(udids)},
            )
            raise DatabaseError("find_existing_device_keys query failed") from exc

        existing_serials: set[str] = set()
        existing_udids: set[str] = set()
        for row in rows:
            if row["serial_number"] is not None:
                existing_serials.add(str(row["serial_number"]))
            if row["udid"] is not None:
                existing_udids.add(str(row["udid"]))

        return ExistingDeviceKeys(serials=existing_serials, udids=existing_udids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
