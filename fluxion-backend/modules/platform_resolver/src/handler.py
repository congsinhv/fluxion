"""Lambda entry point — AppSync field dispatch for platform_resolver.

Fields handled:
  listStates(serviceTypeId: Int)                        → [State!]!
  listPolicies(serviceTypeId: Int)                      → [Policy!]!
  listActions(fromStateId: Int, serviceTypeId: Int)     → [Action!]!
  listServices()                                        → [Service!]!
  updateState(id: Int!, input: UpdateStateInput!)       → State!
  updatePolicy(id: Int!, input: UpdatePolicyInput!)     → Policy!
  updateAction(id: ID!, input: UpdateActionInput!)      → Action!
  updateService(id: Int!, input: UpdateServiceInput!)   → Service!
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from auth import Context, permission_required
from config import DATABASE_URI, POWERTOOLS_SERVICE_NAME
from db import Database
from exceptions import FluxionError, InvalidInputError, UnknownFieldError
from schema_types import (
    ActionResponse,
    ListActionsInput,
    ListPoliciesInput,
    ListStatesInput,
    PolicyResponse,
    ServiceResponse,
    StateResponse,
    UpdateActionInput,
    UpdatePolicyInput,
    UpdateServiceInput,
    UpdateStateInput,
)

logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


# ---------------------------------------------------------------------------
# Row → response helpers
# ---------------------------------------------------------------------------


def _row_to_state(row: dict[str, Any]) -> StateResponse:
    return StateResponse(id=int(row["id"]), name=row["name"])


def _row_to_policy(row: dict[str, Any]) -> PolicyResponse:
    return PolicyResponse(
        id=int(row["id"]),
        name=row["name"],
        stateId=int(row["state_id"]),
        serviceTypeId=int(row["service_type_id"]),
        color=row.get("color"),
    )


def _row_to_action(row: dict[str, Any]) -> ActionResponse:
    cfg = row.get("configuration")
    return ActionResponse(
        id=str(row["id"]),
        name=row["name"],
        actionTypeId=int(row["action_type_id"]),
        fromStateId=int(row["from_state_id"]) if row.get("from_state_id") is not None else None,
        serviceTypeId=int(row["service_type_id"]) if row.get("service_type_id") is not None else None,
        applyPolicyId=int(row["apply_policy_id"]),
        configuration=json.dumps(cfg) if cfg is not None else None,
    )


def _row_to_service(row: dict[str, Any]) -> ServiceResponse:
    return ServiceResponse(id=int(row["id"]), name=row["name"], isEnabled=bool(row["is_enabled"]))


# ---------------------------------------------------------------------------
# Field handlers
# ---------------------------------------------------------------------------


@permission_required("platform:read")
def list_states(args: dict[str, Any], ctx: Context, _cid: str) -> list[dict[str, Any]]:
    try:
        inp = ListStatesInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows = db.list_states(service_type_id=inp.serviceTypeId)
    return [_row_to_state(r).model_dump() for r in rows]


@permission_required("platform:read")
def list_policies(args: dict[str, Any], ctx: Context, _cid: str) -> list[dict[str, Any]]:
    try:
        inp = ListPoliciesInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows = db.list_policies(service_type_id=inp.serviceTypeId)
    return [_row_to_policy(r).model_dump() for r in rows]


@permission_required("platform:read")
def list_actions(args: dict[str, Any], ctx: Context, _cid: str) -> list[dict[str, Any]]:
    try:
        inp = ListActionsInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows = db.list_actions(
            from_state_id=inp.fromStateId,
            service_type_id=inp.serviceTypeId,
        )
    return [_row_to_action(r).model_dump() for r in rows]


@permission_required("platform:read")
def list_services(args: dict[str, Any], ctx: Context, _cid: str) -> list[dict[str, Any]]:
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows = db.list_services()
    return [_row_to_service(r).model_dump() for r in rows]


@permission_required("platform:admin")
def update_state(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = UpdateStateInput.model_validate(args.get("input", {}))
    except Exception as exc:
        # UpdateStateInput.name is required — Pydantic raises ValidationError if missing.
        raise InvalidInputError(str(exc)) from exc
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        row = db.update_state(int(args["id"]), inp.model_dump())
    return _row_to_state(row).model_dump()


@permission_required("platform:admin")
def update_policy(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = UpdatePolicyInput.model_validate(args.get("input", {}))
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    fields = inp.model_dump(exclude_unset=True)
    if not fields:
        raise InvalidInputError("updatePolicy: at least one field must be provided")
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        row = db.update_policy(int(args["id"]), fields)
    return _row_to_policy(row).model_dump()


@permission_required("platform:admin")
def update_action(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = UpdateActionInput.model_validate(args.get("input", {}))
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    fields = inp.model_dump(exclude_unset=True)
    if not fields:
        raise InvalidInputError("updateAction: at least one field must be provided")
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        row = db.update_action(str(args["id"]), fields)
    return _row_to_action(row).model_dump()


@permission_required("platform:admin")
def update_service(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = UpdateServiceInput.model_validate(args.get("input", {}))
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    fields = inp.model_dump(exclude_unset=True)
    if not fields:
        raise InvalidInputError("updateService: at least one field must be provided")
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        row = db.update_service(int(args["id"]), fields)
    return _row_to_service(row).model_dump()


# ---------------------------------------------------------------------------
# Dispatch table + entry point
# ---------------------------------------------------------------------------

FIELD_HANDLERS: dict[str, FieldHandler] = {
    "listStates": list_states,
    "listPolicies": list_policies,
    "listActions": list_actions,
    "listServices": list_services,
    "updateState": update_state,
    "updatePolicy": update_policy,
    "updateAction": update_action,
    "updateService": update_service,
}


def lambda_handler(event: dict[str, Any], context: Any) -> Any:
    """AppSync Lambda direct resolver entry point."""
    correlation_id: str = getattr(context, "aws_request_id", "local")
    field: str = event.get("info", {}).get("fieldName", "")

    logger.info("resolver.invoked", extra={"field": field, "correlation_id": correlation_id})

    try:
        handler = FIELD_HANDLERS.get(field)
        if handler is None:
            raise UnknownFieldError(f"no handler for field: {field!r}")
        result: Any = handler(event.get("arguments", {}), event, correlation_id)
        return result
    except FluxionError as exc:
        logger.warning(
            "resolver.error",
            extra={"field": field, "error_type": exc.code, "correlation_id": correlation_id},
        )
        return exc.to_appsync_error()
