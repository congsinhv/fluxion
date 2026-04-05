"""Lambda handler for upload_processor — SQS-triggered device insertion."""

import json

from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer
from db import DBConnection
from utils import validate_tenant_id


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Process SQS messages — insert devices with device_informations."""
    batch_failures = []
    logger.debug("Event received", extra={"event": event})

    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            body = json.loads(record["body"])
            tenant = validate_tenant_id(body["tenantId"])

            device_id = DBConnection.insert_device_with_info(
                schema_name=tenant,
                serial_number=body["serialNumber"],
                udid=body["udid"],
                name=body.get("name"),
                model=body.get("model"),
                os_version=body.get("osVersion"),
            )

            if device_id:
                logger.info("Device created", extra={"device_id": device_id, "serial": body["serialNumber"]})
            else:
                logger.info("Device skipped (duplicate)", extra={"serial": body["serialNumber"]})

        except Exception:
            logger.exception("Failed to process message", extra={"message_id": message_id})
            batch_failures.append({"itemIdentifier": message_id})

    # SQS partial batch failure reporting
    return {"batchItemFailures": batch_failures}
