"""psycopg3 repository for action_resolver.

Tenant-isolated: every SQL query uses psycopg.sql.Identifier for schema names.
Never use f-string interpolation for schema names (SQL injection defense).

Tables used (per-tenant schema):
  devices           — id UUID, state_id SMALLINT, assigned_action_id UUID
  actions           — id UUID, from_state_id SMALLINT
  batch_actions     — id UUID, batch_id UUID, action_id UUID, created_by TEXT,
                      total_devices INT, status VARCHAR
  batch_device_actions — id UUID, batch_id UUID, device_id UUID, status VARCHAR
  action_executions — id UUID, device_id UUID, action_id UUID,
                      command_uuid UUID, status VARCHAR
  message_templates — id UUID, content TEXT, is_active BOOLEAN

Race-safe device assignment:
  UPDATE devices SET assigned_action_id=... WHERE id=ANY(...) AND assigned_action_id IS NULL
  RETURNING id
Only returned IDs are considered successfully locked; missing IDs go to failed[].
"""

from __future__ import annotations

import base64
import re
import uuid
from datetime import UTC, datetime
from typing import Any, NamedTuple

import psycopg
import psycopg.rows
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, InvalidInputError, TenantNotFoundError

# Matches accesscontrol.tenants.ck_tenants_schema_name_format.
# Bare names only: dev1, acme, fpt (no prefix). See design-patterns.md §11.2.
_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _validate_schema(schema_name: str) -> str:
    """Raise DatabaseError if schema_name fails the safety regex."""
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


# ---------------------------------------------------------------------------
# Cursor helpers for list_action_logs pagination
# ---------------------------------------------------------------------------

_CURSOR_SEP = "|"


def _encode_action_log_cursor(created_at: Any, id_: Any) -> str:
    """Encode a (created_at, id) tuple as a URL-safe base64 cursor token.

    Args:
        created_at: datetime object or ISO string for the last row.
        id_:        UUID or string for the last row's PK.

    Returns:
        URL-safe base64 string suitable for use as ``nextToken``.
    """
    ts = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    raw = f"{ts}{_CURSOR_SEP}{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_action_log_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    """Decode a nextToken cursor back to (created_at, id) tuple.

    Args:
        token: URL-safe base64 cursor string.

    Returns:
        (created_at datetime with UTC tzinfo, id UUID)

    Raises:
        InvalidInputError: Token is malformed, missing separator, or contains
                           invalid datetime/UUID values.
    """
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
    except Exception as exc:
        raise InvalidInputError("invalid nextToken (base64 decode failed)") from exc

    parts = raw.split(_CURSOR_SEP, 1)
    if len(parts) != 2:
        raise InvalidInputError("invalid nextToken (missing separator)")

    ts_str, id_str = parts
    try:
        created_at = datetime.fromisoformat(ts_str)
        # Ensure timezone-aware for SQL comparison.
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
    except ValueError as exc:
        raise InvalidInputError(f"invalid nextToken (bad datetime: {ts_str!r})") from exc

    try:
        id_uuid = uuid.UUID(id_str)
    except ValueError as exc:
        raise InvalidInputError(f"invalid nextToken (bad UUID: {id_str!r})") from exc

    return created_at, id_uuid


class ValidDevice(NamedTuple):
    """A device that passed FSM and availability validation."""

    device_id: str  # UUID as string
    state_id: int


class InvalidDevice(NamedTuple):
    """A device that failed FSM or availability validation."""

    device_id: str  # UUID as string
    reason: str  # human-readable; includes error-code prefix e.g. "DEVICE_NOT_FOUND: ..."


class ExecutionTuple(NamedTuple):
    """Row returned from action_executions INSERT."""

    device_id: str  # UUID as string
    execution_id: str  # action_executions.id
    command_uuid: str  # action_executions.command_uuid


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
            code:        Permission code (e.g. ``"action:execute"``).

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
    # Action-resolver repo methods
    # ------------------------------------------------------------------

    def load_action(self, action_id: str, schema: str) -> dict[str, Any] | None:
        """Load an action row by UUID from the tenant schema.

        Args:
            action_id: UUID string of the action.
            schema:    Validated tenant schema name.

        Returns:
            Row dict with at minimum ``{id, from_state_id}`` or None if not found.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()
        query = psycopg.sql.SQL(
            "SELECT id, name, from_state_id, action_type_id, apply_policy_id "
            "FROM {schema}.actions WHERE id = %s"
        ).format(schema=psycopg.sql.Identifier(schema))
        try:
            with conn.cursor() as cur:
                cur.execute(query, (action_id,))
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.load_action_failed", extra={"action_id": action_id})
            raise DatabaseError("load_action query failed") from exc
        return dict(row) if row else None

    def load_message_template(self, template_id: str, schema: str) -> dict[str, Any] | None:
        """Load a message_template row by UUID from the tenant schema.

        Args:
            template_id: UUID string of the template.
            schema:      Validated tenant schema name.

        Returns:
            Row dict with at minimum ``{id, content, is_active}`` or None if not found.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()
        query = psycopg.sql.SQL(
            "SELECT id, name, content, is_active, notification_type "
            "FROM {schema}.message_templates WHERE id = %s"
        ).format(schema=psycopg.sql.Identifier(schema))
        try:
            with conn.cursor() as cur:
                cur.execute(query, (template_id,))
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.load_message_template_failed", extra={"template_id": template_id})
            raise DatabaseError("load_message_template query failed") from exc
        return dict(row) if row else None

    def validate_devices_for_action(
        self,
        device_ids: list[str],
        action_id: str,
        schema: str,
    ) -> tuple[list[ValidDevice], list[InvalidDevice]]:
        """Classify devices into valid/invalid for the given action.

        Performs a single JOIN query to fetch device state and action's
        from_state_id, then classifies in Python:
          - Not found → ``InvalidDevice(reason="DEVICE_NOT_FOUND: ...")``.
          - state_id != action.from_state_id → ``InvalidDevice(reason="INVALID_TRANSITION: ...")``.
          - Valid (assigned_action_id check is deferred to the race-safe UPDATE).

        NOTE: ``assigned_action_id IS NULL`` is NOT checked here — that race-safe
        check is done in ``create_batch_with_devices`` via UPDATE...WHERE...RETURNING.

        Args:
            device_ids: List of device UUID strings.
            action_id:  Action UUID string.
            schema:     Validated tenant schema name.

        Returns:
            (valid_devices, invalid_devices) tuple.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()

        query = psycopg.sql.SQL(
            """
            SELECT d.id, d.state_id, d.assigned_action_id, a.from_state_id
            FROM   {schema}.devices d
            JOIN   {schema}.actions a ON a.id = %s
            WHERE  d.id = ANY(%s)
            """
        ).format(schema=psycopg.sql.Identifier(schema))

        try:
            with conn.cursor() as cur:
                cur.execute(query, (action_id, device_ids))
                rows = cur.fetchall()
        except psycopg.Error as exc:
            logger.exception(
                "db.validate_devices_failed",
                extra={"action_id": action_id, "count": len(device_ids)},
            )
            raise DatabaseError("validate_devices_for_action query failed") from exc

        found_ids = {str(row["id"]) for row in rows}
        valid: list[ValidDevice] = []
        invalid: list[InvalidDevice] = []

        # Devices not returned by the query are not found in this tenant.
        for did in device_ids:
            if did not in found_ids:
                invalid.append(
                    InvalidDevice(device_id=did, reason=f"DEVICE_NOT_FOUND: device {did} not found")
                )

        for row in rows:
            did = str(row["id"])
            state_id = int(row["state_id"])
            from_state_id = row["from_state_id"]

            # from_state_id may be NULL for Upload action (state-agnostic).
            if from_state_id is not None and state_id != int(from_state_id):
                invalid.append(
                    InvalidDevice(
                        device_id=did,
                        reason=(
                            f"INVALID_TRANSITION: device state {state_id} "
                            f"does not match action from_state {from_state_id}"
                        ),
                    )
                )
            else:
                valid.append(ValidDevice(device_id=did, state_id=state_id))

        return valid, invalid

    def create_batch_with_devices(
        self,
        batch_id: str,
        action_id: str,
        created_by: str,
        valid_devices: list[ValidDevice],
        schema: str,
    ) -> list[ExecutionTuple]:
        """Insert batch_actions + batch_device_actions + action_executions in one transaction.

        Race-safe: uses ``UPDATE devices SET assigned_action_id=... WHERE id=ANY(...)
        AND assigned_action_id IS NULL RETURNING id`` — only locked device IDs
        proceed to INSERT; devices that lost the race are silently excluded here
        (caller gets empty ExecutionTuple for those device_ids and handles them
        as DEVICE_BUSY failures).

        All INSERTs happen inside a single psycopg transaction block.
        On any psycopg error the transaction is rolled back.

        Args:
            batch_id:      UUID string for the batch (batch_actions.batch_id).
            action_id:     Action UUID string.
            created_by:    cognito_sub of the requesting user.
            valid_devices: Devices that passed FSM validation.
            schema:        Validated tenant schema name.

        Returns:
            List of ExecutionTuple for devices that were successfully locked.
            Devices that lost the concurrent-assign race are absent from the list.

        Raises:
            DatabaseError: Any DB error during the transaction; transaction is rolled back.
        """
        _validate_schema(schema)
        conn = self._require_conn()

        if not valid_devices:
            return []

        device_ids = [d.device_id for d in valid_devices]
        # Generate a new batch PK uuid (batch_actions.id) separate from batch_id
        batch_pk = str(uuid.uuid4())

        try:
            with conn.transaction():
                # 1. Race-safe device lock: only returns IDs that were unassigned.
                lock_query = psycopg.sql.SQL(
                    """
                    UPDATE {schema}.devices
                    SET    assigned_action_id = %s
                    WHERE  id = ANY(%s)
                      AND  assigned_action_id IS NULL
                    RETURNING id
                    """
                ).format(schema=psycopg.sql.Identifier(schema))

                with conn.cursor() as cur:
                    cur.execute(lock_query, (action_id, device_ids))
                    locked_rows = cur.fetchall()

                locked_ids = {str(r["id"]) for r in locked_rows}
                locked_devices = [d for d in valid_devices if d.device_id in locked_ids]

                if not locked_devices:
                    # All lost the race — nothing to insert; transaction commits empty.
                    return []

                locked_count = len(locked_devices)

                # 2. INSERT batch_actions (one row per batch).
                ba_query = psycopg.sql.SQL(
                    """
                    INSERT INTO {schema}.batch_actions
                        (id, batch_id, action_id, created_by, total_devices, status)
                    VALUES (%s, %s, %s, %s, %s, 'IN_PROGRESS')
                    """
                ).format(schema=psycopg.sql.Identifier(schema))

                with conn.cursor() as cur:
                    cur.execute(ba_query, (batch_pk, batch_id, action_id, created_by, locked_count))

                # 3. INSERT action_executions and batch_device_actions per locked device.
                ae_query = psycopg.sql.SQL(
                    """
                    INSERT INTO {schema}.action_executions (device_id, action_id, status)
                    VALUES (%s, %s, 'ACTION_PENDING')
                    RETURNING id, command_uuid
                    """
                ).format(schema=psycopg.sql.Identifier(schema))

                bda_query = psycopg.sql.SQL(
                    """
                    INSERT INTO {schema}.batch_device_actions (batch_id, device_id, status)
                    VALUES (%s, %s, 'PENDING')
                    """
                ).format(schema=psycopg.sql.Identifier(schema))

                results: list[ExecutionTuple] = []
                for device in locked_devices:
                    with conn.cursor() as cur:
                        cur.execute(ae_query, (device.device_id, action_id))
                        ae_row = cur.fetchone()

                    if not ae_row:
                        raise DatabaseError(
                            f"action_executions INSERT returned no row for device {device.device_id}"
                        )

                    with conn.cursor() as cur:
                        cur.execute(bda_query, (batch_id, device.device_id))

                    results.append(
                        ExecutionTuple(
                            device_id=device.device_id,
                            execution_id=str(ae_row["id"]),
                            command_uuid=str(ae_row["command_uuid"]),
                        )
                    )

            return results

        except psycopg.Error as exc:
            logger.exception(
                "db.create_batch_with_devices_failed",
                extra={"batch_id": batch_id, "action_id": action_id},
            )
            raise DatabaseError("create_batch_with_devices transaction failed") from exc

    # ------------------------------------------------------------------
    # ActionLog repo methods (P1b)
    # ------------------------------------------------------------------

    def get_action_log_by_batch_id(self, batch_id: str, schema: str) -> dict[str, Any] | None:
        """Load a batch_actions row by batch_id UUID with computed errorCount.

        Args:
            batch_id: UUID string (``batch_actions.batch_id``).
            schema:   Validated tenant schema name.

        Returns:
            Row dict with keys: id, batch_id, action_id, created_by, total_devices,
            error_count, status, created_at.  Returns None if not found.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()
        query = psycopg.sql.SQL(
            """
            SELECT ba.id,
                   ba.batch_id,
                   ba.action_id,
                   ba.created_by,
                   ba.total_devices,
                   ba.status,
                   ba.created_at,
                   COUNT(bda.id) FILTER (WHERE bda.error_code IS NOT NULL) AS error_count
            FROM   {schema}.batch_actions ba
            LEFT JOIN {schema}.batch_device_actions bda ON bda.batch_id = ba.batch_id
            WHERE  ba.batch_id = %s
            GROUP BY ba.id
            """
        ).format(schema=psycopg.sql.Identifier(schema))
        try:
            with conn.cursor() as cur:
                cur.execute(query, (batch_id,))
                row = cur.fetchone()
        except psycopg.Error as exc:
            logger.exception("db.get_action_log_failed", extra={"batch_id": batch_id})
            raise DatabaseError("get_action_log_by_batch_id query failed") from exc
        return dict(row) if row else None

    def list_action_logs(
        self,
        limit: int,
        after_cursor: str | None,
        schema: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """List batch_actions with computed errorCount, ordered newest-first.

        Uses a tuple cursor ``(created_at DESC, id DESC)`` for stable pagination
        under ties.  Fetches N+1 rows to determine whether a next page exists.

        Args:
            limit:        Page size (max rows to return to caller).
            after_cursor: Opaque nextToken from a previous response, or None
                          for the first page.
            schema:       Validated tenant schema name.

        Returns:
            (rows, next_cursor) where next_cursor is None if no more pages.

        Raises:
            InvalidInputError: Cursor is malformed.
            DatabaseError:     Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()

        cursor_filter = psycopg.sql.SQL("")
        cursor_params: tuple[Any, ...] = ()

        if after_cursor:
            cur_created_at, cur_id = _decode_action_log_cursor(after_cursor)
            cursor_filter = psycopg.sql.SQL(
                "AND (ba.created_at, ba.id) < (%s::timestamptz, %s::uuid)"
            )
            cursor_params = (cur_created_at.isoformat(), str(cur_id))

        query = psycopg.sql.SQL(
            """
            SELECT ba.id,
                   ba.batch_id,
                   ba.action_id,
                   ba.created_by,
                   ba.total_devices,
                   ba.status,
                   ba.created_at,
                   COUNT(bda.id) FILTER (WHERE bda.error_code IS NOT NULL) AS error_count
            FROM   {schema}.batch_actions ba
            LEFT JOIN {schema}.batch_device_actions bda ON bda.batch_id = ba.batch_id
            WHERE  TRUE
            {cursor_filter}
            GROUP BY ba.id
            ORDER BY ba.created_at DESC, ba.id DESC
            LIMIT  %s
            """
        ).format(
            schema=psycopg.sql.Identifier(schema),
            cursor_filter=cursor_filter,
        )

        params: tuple[Any, ...] = cursor_params + (limit + 1,)

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            logger.exception("db.list_action_logs_failed")
            raise DatabaseError("list_action_logs query failed") from exc

        raw_rows = [dict(r) for r in rows]
        has_more = len(raw_rows) > limit
        page = raw_rows[:limit]

        next_cursor: str | None = None
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_action_log_cursor(last["created_at"], last["id"])

        return page, next_cursor

    def get_failed_devices_for_batch(self, batch_id: str, schema: str) -> list[dict[str, Any]]:
        """Return failed batch_device_actions rows for CSV report generation.

        Args:
            batch_id: UUID string (``batch_device_actions.batch_id``).
            schema:   Validated tenant schema name.

        Returns:
            List of dicts with keys: device_id, error_code, error_message, finished_at.
            Empty list if no failed rows exist.

        Raises:
            DatabaseError: Query failed.
        """
        _validate_schema(schema)
        conn = self._require_conn()
        query = psycopg.sql.SQL(
            """
            SELECT device_id, error_code, error_message, finished_at
            FROM   {schema}.batch_device_actions
            WHERE  batch_id = %s
              AND  error_code IS NOT NULL
            ORDER BY finished_at
            """
        ).format(schema=psycopg.sql.Identifier(schema))
        try:
            with conn.cursor() as cur:
                cur.execute(query, (batch_id,))
                rows = cur.fetchall()
        except psycopg.Error as exc:
            logger.exception("db.get_failed_devices_failed", extra={"batch_id": batch_id})
            raise DatabaseError("get_failed_devices_for_batch query failed") from exc
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
