"""Lambda handler for action_resolver — executeAction, executeBulkAction."""

from uuid import uuid4

from aws_lambda_powertools.event_handler import AppSyncResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from config import SQS_QUEUE_URL, logger, tracer
from const import ACTION_PENDING, MAX_BULK_DEVICES
from db import DBConnection
from exceptions import (
    ActionNotFoundError,
    DeviceBusyError,
    DeviceNotFoundError,
    FluxionError,
    InvalidTransitionError,
)
from utils import get_tenant, send_message

app = AppSyncResolver()


@app.resolver(type_name="Mutation", field_name="executeAction")
def execute_action(input: dict) -> dict:
    tenant = get_tenant(app)
    device_id = input["deviceId"]
    action_id = input["actionId"]
    try:
        # 1. Get device
        device = DBConnection.get_device_for_action(schema_name=tenant, device_id=device_id)
        if not device:
            raise DeviceNotFoundError(device_id)

        # 2. Guard: device not busy
        if device["assigned_action_id"] is not None:
            raise DeviceBusyError(device_id)

        # 3. Get action + guard: valid transition
        action = DBConnection.get_action_by_id(schema_name=tenant, action_id=action_id)
        if not action:
            raise ActionNotFoundError(action_id)
        if action["from_state_id"] != device["state_id"]:
            raise InvalidTransitionError(device["state_id"], action["name"])

        # TODO: Guard 3 — RBAC (release = admin only) — separate ticket

        # 4. Pre-generate IDs
        execution_id = str(uuid4())
        command_uuid = str(uuid4())

        # 5. Enqueue to SQS
        message_body = {
            "executionId": execution_id,
            "commandUuid": command_uuid,
            "deviceId": device_id,
            "actionId": action_id,
            "configuration": input.get("configuration"),
            "tenantId": tenant,
        }
        send_message(SQS_QUEUE_URL, message_body)

        return {
            "executionId": execution_id,
            "commandUuid": command_uuid,
            "status": ACTION_PENDING,
        }
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in executeAction")
        raise


@app.resolver(type_name="Mutation", field_name="executeBulkAction")
def execute_bulk_action(input: dict) -> dict:
    tenant = get_tenant(app)
    device_ids = input["deviceIds"]
    action_id = input["actionId"]
    configuration = input.get("configuration")

    if len(device_ids) > MAX_BULK_DEVICES:
        raise FluxionError(f"Exceeds max bulk limit of {MAX_BULK_DEVICES}", "VALIDATION_ERROR")

    # Fetch action once outside loop to avoid N+1
    action = DBConnection.get_action_by_id(schema_name=tenant, action_id=action_id)
    if not action:
        raise ActionNotFoundError(action_id)

    valid = []
    failed = []
    for device_id in device_ids:
        try:
            # 1. Get device
            device = DBConnection.get_device_for_action(schema_name=tenant, device_id=device_id)
            if not device:
                raise DeviceNotFoundError(device_id)

            # 2. Guard: device not busy
            if device["assigned_action_id"] is not None:
                raise DeviceBusyError(device_id)

            # 3. Guard: valid transition
            if action["from_state_id"] != device["state_id"]:
                raise InvalidTransitionError(device["state_id"], action["name"])

            # TODO: Guard 3 — RBAC (release = admin only) — separate ticket

            # 4. Pre-generate IDs
            execution_id = str(uuid4())
            command_uuid = str(uuid4())

            # 5. Enqueue to SQS
            message_body = {
                "executionId": execution_id,
                "commandUuid": command_uuid,
                "deviceId": device_id,
                "actionId": action_id,
                "configuration": configuration,
                "tenantId": tenant,
            }
            send_message(SQS_QUEUE_URL, message_body)

            valid.append({
                "executionId": execution_id,
                "commandUuid": command_uuid,
                "status": ACTION_PENDING,
            })
        except FluxionError as e:
            failed.append({"deviceId": device_id, "reason": str(e)})
        except Exception:
            logger.exception(f"Unexpected error for device {device_id}")
            failed.append({"deviceId": device_id, "reason": "Internal error"})

    return {"valid": valid, "failed": failed}


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — dispatches to AppSyncResolver."""
    logger.debug("Event received", extra={"event": event})
    return app.resolve(event, context)
