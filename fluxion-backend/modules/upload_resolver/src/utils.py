"""Utility functions for upload_resolver."""

import json
import re

from config import sqs_client


def send_message(queue_url: str, message_body: dict) -> None:
    """Send a JSON message to an SQS queue."""
    sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only) to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError("Invalid tenant_id format")
    return tenant_id


def get_tenant(app_instance) -> str:
    """Extract and validate tenant_id from JWT claims."""
    tenant_id = app_instance.current_event.identity.claims["custom:tenant_id"]
    return validate_tenant_id(tenant_id)
