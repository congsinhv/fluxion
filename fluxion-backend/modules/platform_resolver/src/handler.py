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

from collections.abc import Callable
from typing import Any

from auth import Context, permission_required, validate_input, validate_patch
from config import logger
from db import Database
from exceptions import FluxionError, UnknownFieldError
from permissions import PERM_PLATFORM_ADMIN, PERM_PLATFORM_READ
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

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


# ---------------------------------------------------------------------------
# Field handlers
# ---------------------------------------------------------------------------


@permission_required(PERM_PLATFORM_READ)
@validate_input(ListStatesInput)
def list_states(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: ListStatesInput
) -> list[dict[str, Any]]:
    with Database() as db:
        rows = db.list_states(service_type_id=inp.serviceTypeId, schema=ctx.tenant_schema)
    return [StateResponse.dump_row(r) for r in rows]


@permission_required(PERM_PLATFORM_READ)
@validate_input(ListPoliciesInput)
def list_policies(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: ListPoliciesInput
) -> list[dict[str, Any]]:
    with Database() as db:
        rows = db.list_policies(service_type_id=inp.serviceTypeId, schema=ctx.tenant_schema)
    return [PolicyResponse.dump_row(r) for r in rows]


@permission_required(PERM_PLATFORM_READ)
@validate_input(ListActionsInput)
def list_actions(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: ListActionsInput
) -> list[dict[str, Any]]:
    with Database() as db:
        rows = db.list_actions(
            from_state_id=inp.fromStateId,
            service_type_id=inp.serviceTypeId,
            schema=ctx.tenant_schema,
        )
    return [ActionResponse.dump_row(r) for r in rows]


@permission_required(PERM_PLATFORM_READ)
def list_services(_args: dict[str, Any], ctx: Context, _cid: str) -> list[dict[str, Any]]:
    with Database() as db:
        rows = db.list_services(schema=ctx.tenant_schema)
    return [ServiceResponse.dump_row(r) for r in rows]


@permission_required(PERM_PLATFORM_ADMIN)
@validate_input(UpdateStateInput, key="input")
def update_state(
    args: dict[str, Any], ctx: Context, _cid: str, inp: UpdateStateInput
) -> dict[str, Any]:
    with Database() as db:
        row = db.update_state(int(args["id"]), inp.model_dump(), schema=ctx.tenant_schema)
    return StateResponse.dump_row(row)


@permission_required(PERM_PLATFORM_ADMIN)
@validate_patch(UpdatePolicyInput, error_prefix="updatePolicy")
def update_policy(
    args: dict[str, Any], ctx: Context, _cid: str, fields: dict[str, Any]
) -> dict[str, Any]:
    with Database() as db:
        row = db.update_policy(int(args["id"]), fields, schema=ctx.tenant_schema)
    return PolicyResponse.dump_row(row)


@permission_required(PERM_PLATFORM_ADMIN)
@validate_patch(UpdateActionInput, error_prefix="updateAction")
def update_action(
    args: dict[str, Any], ctx: Context, _cid: str, fields: dict[str, Any]
) -> dict[str, Any]:
    with Database() as db:
        row = db.update_action(str(args["id"]), fields, schema=ctx.tenant_schema)
    return ActionResponse.dump_row(row)


@permission_required(PERM_PLATFORM_ADMIN)
@validate_patch(UpdateServiceInput, error_prefix="updateService")
def update_service(
    args: dict[str, Any], ctx: Context, _cid: str, fields: dict[str, Any]
) -> dict[str, Any]:
    with Database() as db:
        row = db.update_service(int(args["id"]), fields, schema=ctx.tenant_schema)
    return ServiceResponse.dump_row(row)


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
