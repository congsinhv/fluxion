"""Lambda handler for action_trigger — SQS-triggered execution creation + SNS publish."""

import json

from aws_lambda_powertools.utilities.typing import LambdaContext
from config import SNS_TOPIC_ARN, logger, tracer
from db import DBConnection
from exceptions import DeviceTokensNotFoundError
from utils import send_sns_message, validate_tenant_id


def _process_record(body: dict) -> None:
    """Process a single SQS record — create execution, assign action, publish command."""
    tenant = validate_tenant_id(body["tenantId"])
    device_id = body["deviceId"]
    action_id = body["actionId"]
    execution_id = body["executionId"]
    command_uuid = body["commandUuid"]

    log_ctx = {"execution_id": execution_id, "device_id": device_id, "action_id": action_id}

    # 1. Insert execution + assign action (transactional)
    logger.info("Creating execution and assigning action", extra=log_ctx)
    DBConnection.create_execution_and_assign(tenant, execution_id, command_uuid, device_id, action_id)

    # 2. Get push credentials
    tokens = DBConnection.get_device_tokens(tenant, device_id)
    if not tokens:
        raise DeviceTokensNotFoundError(device_id)
    logger.debug("Device tokens retrieved", extra=log_ctx)

    # 3. Get action details + device UDID
    action = DBConnection.get_action_details(tenant, action_id)
    udid = DBConnection.get_device_udid(tenant, device_id)
    action_name = action["name"] if action else None
    logger.debug("Action details retrieved", extra={**log_ctx, "action_name": action_name, "udid": udid})

    # 4. Publish command to SNS for OEM processor
    message_body = {
        "commandUuid": command_uuid,
        "deviceUdid": udid,
        "pushToken": tokens["push_token"].hex() if tokens.get("push_token") else None,
        "pushMagic": tokens.get("push_magic"),
        "topic": tokens.get("topic"),
        "requestType": action["name"] if action else None,
        "commandPayload": body.get("configuration") or (action.get("configuration") if action else None),
        "tenantId": tenant,
    }
    send_sns_message(SNS_TOPIC_ARN, message_body)

    logger.info("Action triggered — command published to SNS", extra={**log_ctx, "command_uuid": command_uuid})


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Process SQS messages — create executions and publish MDM commands."""
    batch_failures = []
    logger.debug("Event received", extra={"event": event})

    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            body = json.loads(record["body"])
            _process_record(body)
        except Exception:
            logger.exception("Failed to process message", extra={"message_id": message_id})
            batch_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_failures}
