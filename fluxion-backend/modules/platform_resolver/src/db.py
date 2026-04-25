"""psycopg3 repository for platform_resolver.

All tenant-schema table references use psycopg.sql.Identifier — never f-strings.
Real table names (from migration 4768d32c8037, per-tenant schema):
  {tenant}.states    — FSM state config (id SMALLINT, name)
  {tenant}.policies  — FSM policy config (id SMALLINT, name, state_id, service_type_id, color)
  {tenant}.actions   — FSM action config (id UUID, name, action_type_id, ...)
  {tenant}.services  — Service config (id SMALLINT, name, is_enabled)

List queries return ALL rows filtered by optional args (no cursor pagination —
schema declares [T!]! not a Connection type).

Update methods build dynamic UPDATE via psycopg.sql.Composed — column names from
Pydantic field names mapped to snake_case DB columns; values bound via %s.
"""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg
import psycopg.rows
import psycopg.sql

from config import DATABASE_URI, logger
from exceptions import DatabaseError, NotFoundError, TenantNotFoundError

_SCHEMA_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

# Map Pydantic camelCase field names → DB snake_case column names for update inputs.
_POLICY_COL_MAP: dict[str, str] = {
    "name": "name",
    "stateId": "state_id",
    "serviceTypeId": "service_type_id",
    "color": "color",
}

_ACTION_COL_MAP: dict[str, str] = {
    "name": "name",
    "actionTypeId": "action_type_id",
    "fromStateId": "from_state_id",
    "serviceTypeId": "service_type_id",
    "applyPolicyId": "apply_policy_id",
    "configuration": "configuration",
}

_SERVICE_COL_MAP: dict[str, str] = {
    "name": "name",
    "isEnabled": "is_enabled",
}


def _validate_schema(schema_name: str) -> str:
    if not _SCHEMA_NAME_RE.fullmatch(schema_name):
        raise DatabaseError(f"invalid schema_name: {schema_name!r}")
    return schema_name


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
    # accesscontrol helpers (identical to device_resolver template)
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
    # List queries — return all rows (optional filter); no pagination
    # ------------------------------------------------------------------

    def list_states(
        self, service_type_id: int | None = None, *, schema: str
    ) -> list[dict[str, Any]]:
        """Return all states rows, optionally filtered via policies join.

        Note: states table has no service_type_id column. Filter by service_type_id
        is achieved via a join to policies (states reachable by the given service).
        If no filter, return all states ordered by id.
        """
        schema_id = psycopg.sql.Identifier(schema)
        conn = self._require_conn()
        if service_type_id is not None:
            query = psycopg.sql.SQL(
                """
                SELECT DISTINCT s.id, s.name
                FROM {schema}.states s
                JOIN {schema}.policies p ON p.state_id = s.id
                WHERE p.service_type_id = %s
                ORDER BY s.id
                """
            ).format(schema=schema_id)
            params: list[Any] = [service_type_id]
        else:
            query = psycopg.sql.SQL("SELECT id, name FROM {schema}.states ORDER BY id").format(
                schema=schema_id
            )
            params = []
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_states_failed")
            raise DatabaseError("list_states query failed") from exc

    def list_policies(
        self, service_type_id: int | None = None, *, schema: str
    ) -> list[dict[str, Any]]:
        """Return all policies rows, optionally filtered by service_type_id."""
        schema_id = psycopg.sql.Identifier(schema)
        conn = self._require_conn()
        if service_type_id is not None:
            query = psycopg.sql.SQL(
                """
                SELECT id, name, state_id, service_type_id, color
                FROM {schema}.policies
                WHERE service_type_id = %s
                ORDER BY id
                """
            ).format(schema=schema_id)
            params: list[Any] = [service_type_id]
        else:
            query = psycopg.sql.SQL(
                "SELECT id, name, state_id, service_type_id, color FROM {schema}.policies ORDER BY id"
            ).format(schema=schema_id)
            params = []
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_policies_failed")
            raise DatabaseError("list_policies query failed") from exc

    def list_actions(
        self,
        from_state_id: int | None = None,
        service_type_id: int | None = None,
        *,
        schema: str,
    ) -> list[dict[str, Any]]:
        """Return all actions rows, optionally filtered by from_state_id and/or service_type_id."""
        schema_id = psycopg.sql.Identifier(schema)
        conn = self._require_conn()

        clauses: list[psycopg.sql.Composable] = []
        params: list[Any] = []
        if from_state_id is not None:
            clauses.append(psycopg.sql.SQL("from_state_id = %s"))
            params.append(from_state_id)
        if service_type_id is not None:
            clauses.append(psycopg.sql.SQL("service_type_id = %s"))
            params.append(service_type_id)

        where: psycopg.sql.Composable = psycopg.sql.SQL("")
        if clauses:
            where = psycopg.sql.SQL(" WHERE ") + psycopg.sql.SQL(" AND ").join(clauses)

        query = psycopg.sql.SQL(
            """
            SELECT id, name, action_type_id, from_state_id, service_type_id,
                   apply_policy_id, configuration
            FROM {schema}.actions
            {where}
            ORDER BY name
            """
        ).format(schema=schema_id, where=where)
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_actions_failed")
            raise DatabaseError("list_actions query failed") from exc

    def list_services(self, *, schema: str) -> list[dict[str, Any]]:
        """Return all services rows ordered by id."""
        schema_id = psycopg.sql.Identifier(schema)
        conn = self._require_conn()
        query = psycopg.sql.SQL(
            "SELECT id, name, is_enabled FROM {schema}.services ORDER BY id"
        ).format(schema=schema_id)
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                return [dict(r) for r in cur.fetchall()]
        except psycopg.Error as exc:
            logger.exception("db.list_services_failed")
            raise DatabaseError("list_services query failed") from exc

    # ------------------------------------------------------------------
    # Update mutations — dynamic PATCH via psycopg.sql.Composed
    # ------------------------------------------------------------------

    def update_state(self, state_id: int, fields: dict[str, Any], *, schema: str) -> dict[str, Any]:
        """Update states row by SMALLINT id; return updated row.

        UpdateStateInput.name is required (String!) so fields always contains name.
        """
        # Column names are code-controlled (from Pydantic field keys) — safe to use Identifier.
        col_map = {"name": "name"}
        return self._update_row("states", "id", state_id, fields, col_map, schema=schema)

    def update_policy(
        self, policy_id: int, fields: dict[str, Any], *, schema: str
    ) -> dict[str, Any]:
        """Update policies row by SMALLINT id; return updated row (PATCH semantics)."""
        return self._update_row("policies", "id", policy_id, fields, _POLICY_COL_MAP, schema=schema)

    def update_action(
        self, action_id: str, fields: dict[str, Any], *, schema: str
    ) -> dict[str, Any]:
        """Update actions row by UUID id; return updated row (PATCH semantics).

        configuration is JSONB — serialise str value to JSON before binding.
        """
        if "configuration" in fields and fields["configuration"] is not None:
            # Pydantic may pass a JSON string; psycopg3 expects a Python object for JSONB.
            val = fields["configuration"]
            if isinstance(val, str):
                try:
                    fields = {**fields, "configuration": json.loads(val)}
                except json.JSONDecodeError as exc:
                    from exceptions import InvalidInputError  # noqa: PLC0415

                    raise InvalidInputError(f"configuration is not valid JSON: {val!r}") from exc
        return self._update_row("actions", "id", action_id, fields, _ACTION_COL_MAP, schema=schema)

    def update_service(
        self, service_id: int, fields: dict[str, Any], *, schema: str
    ) -> dict[str, Any]:
        """Update services row by SMALLINT id; return updated row (PATCH semantics)."""
        return self._update_row(
            "services", "id", service_id, fields, _SERVICE_COL_MAP, schema=schema
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_row(
        self,
        table: str,
        pk_col: str,
        pk_val: Any,
        fields: dict[str, Any],
        col_map: dict[str, str],
        *,
        schema: str,
    ) -> dict[str, Any]:
        """Build and execute a dynamic UPDATE … RETURNING * for the given table.

        Args:
            table:   Table name (code-controlled string → Identifier).
            pk_col:  Primary key column name.
            pk_val:  Primary key value to match.
            fields:  Dict of Pydantic camelCase field names → values (exclude_unset).
            col_map: Mapping from camelCase name → snake_case DB column name.
        """
        schema_id = psycopg.sql.Identifier(schema)
        conn = self._require_conn()

        # Map camelCase fields to DB column names; skip unknown keys.
        db_fields = {col_map[k]: v for k, v in fields.items() if k in col_map}

        set_clauses = psycopg.sql.SQL(", ").join(
            psycopg.sql.SQL("{col} = %s").format(col=psycopg.sql.Identifier(col))
            for col in db_fields
        )
        params: list[Any] = list(db_fields.values())
        params.append(pk_val)

        query = psycopg.sql.SQL(
            "UPDATE {schema}.{table} SET {set} WHERE {pk} = %s RETURNING *"
        ).format(
            schema=schema_id,
            table=psycopg.sql.Identifier(table),
            set=set_clauses,
            pk=psycopg.sql.Identifier(pk_col),
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                conn.commit()
        except psycopg.Error as exc:
            logger.exception("db.update_row_failed", extra={"table": table, "pk_val": str(pk_val)})
            raise DatabaseError(f"update {table} failed") from exc

        if not row:
            raise NotFoundError(f"{table} id={pk_val!r}")
        return dict(row)

    def _require_conn(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            raise DatabaseError("Database used outside context manager")
        return self._conn
