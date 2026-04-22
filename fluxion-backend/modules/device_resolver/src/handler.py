"""Lambda entry point — AppSync field dispatch for device_resolver.

Fields handled:
  getDevice(id)                         → DeviceResponse
  listDevices(filter, limit, nextToken) → DeviceConnectionResponse
  getDeviceHistory(deviceId, limit, nextToken) → MilestoneConnectionResponse
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
    DeviceConnectionResponse,
    DeviceInformationResponse,
    DeviceResponse,
    GetDeviceHistoryInput,
    GetDeviceInput,
    ListDevicesInput,
    MilestoneConnectionResponse,
    MilestoneResponse,
)

logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


def _to_iso(value: object) -> str | None:
    """Convert datetime or str to ISO-8601 with T separator, or None.

    psycopg3 returns real datetime objects; AppSync AWSDateTime requires the
    T separator — str(datetime) uses a space instead. Call .isoformat() directly.
    """
    if value is None:
        return None
    # Import inline to keep the type checker satisfied without broadening the param type.
    from datetime import date  # noqa: PLC0415

    if isinstance(value, date):  # covers datetime (subclass) and date
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Row → response helpers
# ---------------------------------------------------------------------------


def _row_to_device(row: dict[str, Any]) -> DeviceResponse:
    info: DeviceInformationResponse | None = None
    if row.get("di_id") is not None:
        ext = row.get("ext_fields")
        info = DeviceInformationResponse(
            id=str(row["di_id"]),
            deviceId=str(row["id"]),
            serialNumber=row["serial_number"] or "",
            udid=row["udid"] or "",
            name=row.get("di_name"),
            model=row.get("model"),
            osVersion=row.get("os_version"),
            batteryLevel=row.get("battery_level"),
            wifiMac=row.get("wifi_mac"),
            isSupervised=row.get("is_supervised"),
            lastCheckinAt=_to_iso(row.get("last_checkin_at")),
            extFields=json.dumps(ext) if ext is not None else None,
        )
    return DeviceResponse(
        id=str(row["id"]),
        createdAt=_to_iso(row["created_at"]) or "",
        updatedAt=_to_iso(row["updated_at"]) or "",
        information=info,
    )


def _row_to_milestone(row: dict[str, Any]) -> MilestoneResponse:
    ext = row.get("ext_fields")
    return MilestoneResponse(
        id=str(row["id"]),
        deviceId=str(row["device_id"]),
        assignedActionId=str(row["assigned_action_id"]) if row.get("assigned_action_id") else None,
        policyId=row.get("policy_id"),
        createdAt=_to_iso(row["created_at"]) or "",
        extFields=json.dumps(ext) if ext is not None else None,
    )


# ---------------------------------------------------------------------------
# Field handlers — each decorated with @permission_required("device:read")
# ---------------------------------------------------------------------------


@permission_required("device:read")
def get_device(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    inp = GetDeviceInput.model_validate(args)
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        row = db.get_device_by_id(inp.id)
    return _row_to_device(row).model_dump()


@permission_required("device:read")
def list_devices(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = ListDevicesInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    f = inp.filter
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows, next_token = db.list_devices(
            limit=inp.limit,
            after_id=inp.nextToken,
            state_id=f.stateId if f else None,
            policy_id=f.policyId if f else None,
            search=f.search if f else None,
        )
    items = [_row_to_device(r) for r in rows]
    return DeviceConnectionResponse(
        items=items, nextToken=next_token, totalCount=len(items)
    ).model_dump()


@permission_required("device:read")
def get_device_history(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = GetDeviceHistoryInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc
    with Database(dsn=DATABASE_URI, tenant_schema=ctx.tenant_schema) as db:
        rows, next_token = db.get_device_history(
            device_id=inp.deviceId,
            limit=inp.limit,
            after_id=inp.nextToken,
        )
    items = [_row_to_milestone(r) for r in rows]
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
