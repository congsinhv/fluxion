"""Utility functions for action_trigger."""

import json
import re

from config import sns_client


def send_sns_message(topic_arn: str, message_body: dict) -> None:
    """Publish a JSON message to an SNS topic."""
    sns_client.publish(TopicArn=topic_arn, Message=json.dumps(message_body))


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only) to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError("Invalid tenant_id format")
    return tenant_id
