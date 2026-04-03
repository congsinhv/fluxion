"""Lambda handler for device_resolver — getDevice, listDevices, getDeviceHistory, listAvailableActions."""

from aws_lambda_powertools.event_handler import AppSyncResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer
from const import DEFAULT_LIMIT, MAX_LIMIT
from db import DBConnection
from exceptions import DeviceNotFoundError, FluxionError
from utils import (
    decode_next_token,
    encode_next_token,
    format_action,
    format_device,
    format_device_list_item,
    format_milestone,
    validate_tenant_id,
)

app = AppSyncResolver()


def _get_tenant(app_instance: AppSyncResolver) -> str:
    """Extract and validate tenant_id from JWT claims."""
    tenant_id = app_instance.current_event.identity.claims["custom:tenant_id"]
    return validate_tenant_id(tenant_id)


@app.resolver(type_name="Query", field_name="getDevice")
def get_device(id: str) -> dict:
    tenant = _get_tenant(app)
    try:
        row = DBConnection.get_device_by_id(schema_name=tenant, device_id=id)
        if not row:
            raise DeviceNotFoundError(id)
        return format_device(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in getDevice")
        raise


@app.resolver(type_name="Query", field_name="listDevices")
def list_devices(
    filter: dict | None = None,
    limit: int = DEFAULT_LIMIT,
    nextToken: str | None = None,  # noqa: N803
) -> dict:
    tenant = _get_tenant(app)
    limit = min(limit, MAX_LIMIT)
    try:
        offset = decode_next_token(nextToken)
        state_id = filter.get("stateId") if filter else None
        policy_id = filter.get("policyId") if filter else None
        search = filter.get("search") if filter else None

        rows = DBConnection.list_devices(
            schema_name=tenant,
            state_id=state_id,
            policy_id=policy_id,
            search=search,
            limit=limit,
            offset=offset,
        )

        has_more = len(rows) > limit
        items = [format_device_list_item(r) for r in rows[:limit]]
        new_token = encode_next_token(offset + limit) if has_more else None

        total_count = DBConnection.count_devices(
            schema_name=tenant,
            state_id=state_id,
            policy_id=policy_id,
            search=search,
        )

        return {"items": items, "nextToken": new_token, "totalCount": total_count}
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listDevices")
        raise


@app.resolver(type_name="Query", field_name="getDeviceHistory")
def get_device_history(
    deviceId: str, limit: int = DEFAULT_LIMIT, nextToken: str | None = None  # noqa: N803
) -> dict:
    tenant = _get_tenant(app)
    limit = min(limit, MAX_LIMIT)
    try:
        offset = decode_next_token(nextToken)
        rows, _ = DBConnection.get_device_history(
            schema_name=tenant, device_id=deviceId, limit=limit, offset=offset
        )

        has_more = len(rows) > limit
        items = [format_milestone(r) for r in rows[:limit]]
        new_token = encode_next_token(offset + limit) if has_more else None

        return {"items": items, "nextToken": new_token}
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in getDeviceHistory")
        raise


@app.resolver(type_name="Query", field_name="listAvailableActions")
def list_available_actions(deviceId: str) -> list[dict]:  # noqa: N803
    tenant = _get_tenant(app)
    try:
        # First get the device to find its current state
        device_row = DBConnection.get_device_by_id(schema_name=tenant, device_id=deviceId)
        if not device_row:
            raise DeviceNotFoundError(deviceId)

        rows = DBConnection.list_available_actions(
            schema_name=tenant, device_state_id=device_row["state_id"]
        )
        return [format_action(r) for r in rows]
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listAvailableActions")
        raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — dispatches to AppSyncResolver."""
    logger.debug("Event received", extra={"event": event})
    return app.resolve(event, context)
