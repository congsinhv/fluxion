"""psycopg3 repository for device_resolver.

All tenant-schema table references use psycopg.sql.Identifier — never f-strings.
Real table names (from migration 4768d32c8037):
  {tenant}.devices            — business state
  {tenant}.device_informations — MDM details (one-to-one with devices)
  {tenant}.milestones         — FSM history per device

Cursor pagination (all three methods):
  nextToken = base64(last_id_bytes)  where last_id is a UUID string.
  On input, decode + UUID-validate; reject malformed tokens with InvalidInputError.
"""

from __future__ import annotations

import base64
import re
import uuid
from typing import Any

import psycopg
import psycopg.rows
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, InvalidInputError, NotFoundError, TenantNotFoundError

_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _validate_schema(schema_name: str) -> str:
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


def _encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(last_id.encode()).decode()


def _decode_cursor(token: str) -> str:
    """Decode a nextToken cursor; raise InvalidInputError if malformed."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        uuid.UUID(raw)  # validate UUID format
        return raw
    except Exception as exc:
        raise InvalidInputError(f"invalid nextToken: {token!r}") from exc


class Database:
    """psycopg3 connection bound to a single Lambda invocation.

    Context-manager only — do not use outside ``with Database(...) as db:``.
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
    # accesscontrol helpers (identical to template)
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
    # Device queries
    # ------------------------------------------------------------------

    def get_device_by_id(self, device_id: str, *, schema: str) -> dict[str, Any]:
        """Fetch device + device_information by device UUID.

        Raises:
            NotFoundError: No device row for device_id.
            DatabaseError: Query execution failed.
        """
        schema = psycopg.sql.Identifier(schema)
        conn = self._require_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    psycopg.sql.SQL(
                        """
                        SELECT
                            d.id,
                            d.created_at,
                            d.updated_at,
                            di.id            AS di_id,
                            di.serial_number,
                            di.udid,
                            di.name          AS di_name,
                            di.model,
                            di.os_version,
                            di.battery_level,
                            di.wifi_mac,
                            di.is_supervised,
                            di.last_checkin_at,
                            di.ext_fields
                        FROM {schema}.devices d
                        LEFT JOIN {schema}.device_informations di ON di.device_id = d.id
                        WHERE d.id = %s
                        """
                    ).format(schema=schema),
                    (device_id,),
                )
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.get_device_by_id_failed", extra={"device_id": device_id})
            raise DatabaseError("get_device query failed") from exc
        if not row:
            raise NotFoundError(f"device {device_id!r}")
        return dict(row)

    def list_devices(
        self,
        limit: int,
        after_id: str | None,
        state_id: int | None = None,
        policy_id: int | None = None,
        search: str | None = None,
        *,
        schema: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return (rows, next_token) for cursor-paginated device list.

        Cursor is based on device.id (UUID ordering — stable for keyset pagination).
        Filters are AND-combined when provided.

        Returns:
            Tuple of (rows, nextToken | None).
        """
        schema = psycopg.sql.Identifier(schema)
        after_uuid = _decode_cursor(after_id) if after_id else None
        conn = self._require_conn()

        conditions: psycopg.sql.Composable = psycopg.sql.SQL("")
        params: list[Any] = []

        clauses: list[psycopg.sql.Composable] = []
        if after_uuid is not None:
            clauses.append(psycopg.sql.SQL("d.id > %s"))
            params.append(after_uuid)
        if state_id is not None:
            clauses.append(psycopg.sql.SQL("d.state_id = %s"))
            params.append(state_id)
        if policy_id is not None:
            clauses.append(psycopg.sql.SQL("d.current_policy_id = %s"))
            params.append(policy_id)
        if search is not None:
            clauses.append(psycopg.sql.SQL("di.serial_number ILIKE %s"))
            params.append(f"%{search}%")

        if clauses:
            conditions = psycopg.sql.SQL(" WHERE ") + psycopg.sql.SQL(" AND ").join(clauses)

        params.append(limit + 1)  # fetch one extra to detect next page

        query = psycopg.sql.SQL(
            """
            SELECT
                d.id,
                d.created_at,
                d.updated_at,
                di.id            AS di_id,
                di.serial_number,
                di.udid,
                di.name          AS di_name,
                di.model,
                di.os_version,
                di.battery_level,
                di.wifi_mac,
                di.is_supervised,
                di.last_checkin_at,
                di.ext_fields
            FROM {schema}.devices d
            LEFT JOIN {schema}.device_informations di ON di.device_id = d.id
            {conditions}
            ORDER BY d.id
            LIMIT %s
            """
        ).format(schema=schema, conditions=conditions)

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_devices_failed")
            raise DatabaseError("list_devices query failed") from exc

        next_token: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_token = _encode_cursor(str(rows[-1]["id"]))

        return rows, next_token

    def get_device_history(
        self,
        device_id: str,
        limit: int,
        after_id: str | None,
        *,
        schema: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return (milestone_rows, next_token) for cursor-paginated history.

        Ordered by created_at DESC, id DESC (chronological history, newest first).
        Cursor encodes the last item's id (UUID).

        Returns:
            Tuple of (rows, nextToken | None).
        """
        schema = psycopg.sql.Identifier(schema)
        after_uuid = _decode_cursor(after_id) if after_id else None
        conn = self._require_conn()

        params: list[Any] = [device_id]
        extra_clause: psycopg.sql.Composable = psycopg.sql.SQL("")

        if after_uuid is not None:
            # Keyset: exclude the after_id row using (created_at, id) tuple comparison
            extra_clause = psycopg.sql.SQL(
                " AND (m.created_at, m.id) < "
                "(SELECT created_at, id FROM {schema}.milestones WHERE id = %s)"
            ).format(schema=schema)
            params.append(after_uuid)

        params.append(limit + 1)

        query = psycopg.sql.SQL(
            """
            SELECT m.id, m.device_id, m.assigned_action_id, m.policy_id,
                   m.created_at, m.ext_fields
            FROM {schema}.milestones m
            WHERE m.device_id = %s
            {extra}
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT %s
            """
        ).format(schema=schema, extra=extra_clause)

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception(
                "db.get_device_history_failed", extra={"device_id": device_id}
            )
            raise DatabaseError("get_device_history query failed") from exc

        next_token: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_token = _encode_cursor(str(rows[-1]["id"]))

        return rows, next_token

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
