"""Lambda entry point — AppSync field dispatch for device_resolver.

Fields handled:
  getDevice(id)                         → DeviceResponse
  listDevices(filter, limit, nextToken) → DeviceConnectionResponse
  getDeviceHistory(deviceId, limit, nextToken) → MilestoneConnectionResponse
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from auth import Context, permission_required, validate_input
from config import logger
from db import Database
from exceptions import FluxionError, UnknownFieldError
from permissions import PERM_DEVICE_READ
from schema_types import (
    DeviceConnectionResponse,
    DeviceResponse,
    GetDeviceHistoryInput,
    GetDeviceInput,
    ListDevicesInput,
    MilestoneConnectionResponse,
    MilestoneResponse,
)

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


# ---------------------------------------------------------------------------
# Field handlers
# ---------------------------------------------------------------------------


@permission_required(PERM_DEVICE_READ)
@validate_input(GetDeviceInput)
def get_device(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: GetDeviceInput
) -> dict[str, Any]:
    with Database() as db:
        row = db.get_device_by_id(inp.id, schema=ctx.tenant_schema)
    return DeviceResponse.dump_row(row)


@permission_required(PERM_DEVICE_READ)
@validate_input(ListDevicesInput)
def list_devices(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: ListDevicesInput
) -> dict[str, Any]:
    f = inp.filter
    with Database() as db:
        rows, next_token = db.list_devices(
            limit=inp.limit,
            after_id=inp.nextToken,
            state_id=f.stateId if f else None,
            policy_id=f.policyId if f else None,
            search=f.search if f else None,
            schema=ctx.tenant_schema,
        )
    items = [DeviceResponse.from_row(r) for r in rows]
    return DeviceConnectionResponse(
        items=items, nextToken=next_token, totalCount=len(items)
    ).model_dump()


@permission_required(PERM_DEVICE_READ)
@validate_input(GetDeviceHistoryInput)
def get_device_history(
    _args: dict[str, Any], ctx: Context, _cid: str, inp: GetDeviceHistoryInput
) -> dict[str, Any]:
    with Database() as db:
        rows, next_token = db.get_device_history(
            device_id=inp.deviceId,
            limit=inp.limit,
            after_id=inp.nextToken,
            schema=ctx.tenant_schema,
        )
    items = [MilestoneResponse.from_row(r) for r in rows]
    return MilestoneConnectionResponse(items=items, nextToken=next_token).model_dump()


# ---------------------------------------------------------------------------
# Dispatch table + entry point
# ---------------------------------------------------------------------------

FIELD_HANDLERS: dict[str, FieldHandler] = {
    "getDevice": get_device,
    "listDevices": list_devices,
    "getDeviceHistory": get_device_history,
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AppSync Lambda direct resolver entry point."""
    correlation_id: str = getattr(context, "aws_request_id", "local")
    field: str = event.get("info", {}).get("fieldName", "")

    logger.info("resolver.invoked", extra={"field": field, "correlation_id": correlation_id})

    try:
        handler = FIELD_HANDLERS.get(field)
        if handler is None:
            raise UnknownFieldError(f"no handler for field: {field!r}")
        result: dict[str, Any] = handler(event.get("arguments", {}), event, correlation_id)
        return result
    except FluxionError as exc:
        logger.warning(
            "resolver.error",
            extra={"field": field, "error_type": exc.code, "correlation_id": correlation_id},
        )
        return exc.to_appsync_error()
