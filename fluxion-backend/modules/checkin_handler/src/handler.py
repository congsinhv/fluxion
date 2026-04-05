"""Lambda handler for checkin_handler — SQS-triggered OEM event processing."""

import json

from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer
from const import (
    ACTION_COMPLETED,
    ACTION_FAILED,
    EVENT_ACTION_COMPLETED,
    EVENT_ACTION_FAILED,
    EVENT_DEVICE_RELEASED,
    EVENT_DEVICE_TOKEN_UPDATE,
    RELEASED_POLICY_ID,
    RELEASED_STATE_ID,
)
from db import DBConnection
from exceptions import ExecutionNotFoundError, UnknownEventTypeError
from utils import call_appsync_mutation, validate_tenant_id

# GraphQL mutations for AppSync subscriptions
NOTIFY_DEVICE_STATE = """
    mutation NotifyDeviceStateChanged($deviceId: ID!, $stateId: Int!, $currentPolicyId: Int!) {
        notifyDeviceStateChanged(deviceId: $deviceId, stateId: $stateId, currentPolicyId: $currentPolicyId) { id }
    }
"""

NOTIFY_EXECUTION_UPDATED = """
    mutation NotifyActionExecutionUpdated($deviceId: ID!, $executionId: ID!, $status: ActionStatus!) {
        notifyActionExecutionUpdated(deviceId: $deviceId, executionId: $executionId, status: $status) { id }
    }
"""


def _handle_token_update(tenant: str, device_id: str, payload: dict) -> None:
    """UPSERT device tokens from OEM check-in."""
    push_token = bytes.fromhex(payload["pushToken"]) if payload.get("pushToken") else None
    unlock_token = bytes.fromhex(payload["unlockToken"]) if payload.get("unlockToken") else None

    DBConnection.update_device_token(
        schema_name=tenant,
        device_id=device_id,
        push_token=push_token,
        push_magic=payload.get("pushMagic"),
        topic=payload.get("topic"),
        unlock_token=unlock_token,
    )
    logger.info("Device tokens updated", extra={"device_id": device_id})


def _handle_device_released(tenant: str, device_id: str, payload: dict) -> None:
    """Release device — update state and notify subscribers."""
    DBConnection.update_device(
        tenant, device_id,
        state_id=RELEASED_STATE_ID,
        current_policy_id=RELEASED_POLICY_ID,
        assigned_action_id=None,
    )
    logger.info("Device released", extra={"device_id": device_id})

    call_appsync_mutation(NOTIFY_DEVICE_STATE, {
        "deviceId": device_id,
        "stateId": RELEASED_STATE_ID,
        "currentPolicyId": RELEASED_POLICY_ID,
    })


def _handle_action_completed(tenant: str, device_id: str, payload: dict) -> None:
    """Complete action — update execution, apply policy, create milestone, notify."""
    command_uuid = payload["commandUuid"]

    # 1. Mark execution as completed
    execution = DBConnection.update_action_execution(tenant, command_uuid, ACTION_COMPLETED)
    if not execution:
        raise ExecutionNotFoundError(command_uuid)

    execution_id = str(execution["id"])
    action_id = str(execution["action_id"])
    logger.info("Execution completed", extra={"execution_id": execution_id, "command_uuid": command_uuid})

    # 2. Get action's target policy and apply to device
    policy = DBConnection.get_action_policy(tenant, action_id)
    if not policy:
        logger.warning("Action policy not found, skipping state update", extra={"action_id": action_id})
        return

    state_id = policy["state_id"]
    policy_id = policy["apply_policy_id"]

    DBConnection.update_device(
        tenant, device_id,
        state_id=state_id,
        current_policy_id=policy_id,
        assigned_action_id=None,
    )

    # 3. Record milestone for device history
    DBConnection.insert_milestone(tenant, device_id, action_id, policy_id)

    # 4. Notify subscribers
    call_appsync_mutation(NOTIFY_DEVICE_STATE, {
        "deviceId": device_id,
        "stateId": state_id,
        "currentPolicyId": policy_id,
    })
    call_appsync_mutation(NOTIFY_EXECUTION_UPDATED, {
        "deviceId": device_id,
        "executionId": execution_id,
        "status": ACTION_COMPLETED,
    })


def _handle_action_failed(tenant: str, device_id: str, payload: dict) -> None:
    """Fail action — update execution, clear assigned action, notify."""
    command_uuid = payload["commandUuid"]

    # 1. Mark execution as failed
    execution = DBConnection.update_action_execution(tenant, command_uuid, ACTION_FAILED)
    if not execution:
        raise ExecutionNotFoundError(command_uuid)

    execution_id = str(execution["id"])
    logger.info("Execution failed", extra={
        "execution_id": execution_id,
        "command_uuid": command_uuid,
        "error": payload.get("errorMessage"),
    })

    # 2. Clear assigned action on device
    DBConnection.update_device(tenant, device_id, assigned_action_id=None)

    # 3. Notify subscribers (execution update only, not device state)
    call_appsync_mutation(NOTIFY_EXECUTION_UPDATED, {
        "deviceId": device_id,
        "executionId": execution_id,
        "status": ACTION_FAILED,
    })


EVENT_HANDLERS = {
    EVENT_DEVICE_TOKEN_UPDATE: _handle_token_update,
    EVENT_DEVICE_RELEASED: _handle_device_released,
    EVENT_ACTION_COMPLETED: _handle_action_completed,
    EVENT_ACTION_FAILED: _handle_action_failed,
}


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Process SQS messages — dispatch to event-type-specific handlers."""
    batch_failures = []
    logger.debug("Event received", extra={"record_count": len(event.get("Records", []))})

    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            body = json.loads(record["body"])
            tenant = validate_tenant_id(body["tenantId"])
            event_type = body["eventType"]
            device_id = body["deviceId"]
            payload = body.get("payload", {})

            handler_fn = EVENT_HANDLERS.get(event_type)
            if not handler_fn:
                raise UnknownEventTypeError(event_type)

            logger.info("Processing event", extra={
                "event_type": event_type, "device_id": device_id, "message_id": message_id,
            })
            handler_fn(tenant, device_id, payload)

        except Exception:
            logger.exception("Failed to process message", extra={"message_id": message_id})
            batch_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_failures}
