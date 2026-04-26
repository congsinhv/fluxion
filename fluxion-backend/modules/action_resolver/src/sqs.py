"""Thin boto3 SQS wrapper for action_resolver.

Sends action-trigger messages to the configured SQS queue.
Each message envelope (locked in GH-35 architectural decision #9):

    {
      "batchId":        <str UUID>,
      "deviceId":       <str UUID>,
      "actionId":       <str UUID>,
      "executionId":    <str UUID>,
      "commandUuid":    <str UUID>,
      "configuration":  <dict | null>,
      "messageContent": <str | null>,   # only present when messageTemplateId was provided
      "tenant_schema":  <str>
    }

SQS errors after DB commit are logged but NOT re-raised to the handler —
the user request already succeeded. Dead PENDING rows are surfaced by the
ActionLog error report (P1b). See phase-01a-action-resolver-assign.md.
"""

from __future__ import annotations

import json
from typing import Any

from config import ACTION_TRIGGER_QUEUE_URL, logger
from exceptions import SqsError

# Lazy-init client: instantiated on first send, reused within the Lambda container.
_client: Any = None


def _get_client() -> Any:
    """Return (or create) the boto3 SQS client.

    Lazy init avoids import-time boto3 calls during unit tests.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        import boto3  # deferred to avoid import cost when SQS is not needed

        _client = boto3.client("sqs")
    return _client


def enqueue_action_trigger(message_body: dict[str, Any], queue_url: str | None = None) -> str:
    """Send a single action-trigger message to SQS.

    Args:
        message_body: Dict conforming to the SQS envelope schema (see module docstring).
        queue_url:    Override queue URL (used in tests); defaults to ACTION_TRIGGER_QUEUE_URL.

    Returns:
        SQS ``MessageId`` string.

    Raises:
        SqsError: boto3 ``ClientError`` from SQS; caller should catch, log, and
                  continue — the DB commit has already occurred.
    """
    url = queue_url or ACTION_TRIGGER_QUEUE_URL
    try:
        response: dict[str, Any] = _get_client().send_message(
            QueueUrl=url,
            MessageBody=json.dumps(message_body),
        )
        return str(response["MessageId"])
    except Exception as exc:
        # Import botocore lazily — it's always present when boto3 is installed.
        try:
            from botocore.exceptions import ClientError

            if isinstance(exc, ClientError):
                logger.error(
                    "sqs.send_message_failed",
                    extra={
                        "device_id": message_body.get("deviceId"),
                        "batch_id": message_body.get("batchId"),
                        "error": str(exc),
                    },
                )
                raise SqsError(f"SQS send_message failed: {exc}") from exc
        except ImportError:
            pass
        logger.error(
            "sqs.send_message_unexpected_error",
            extra={"error": str(exc)},
        )
        raise SqsError(f"SQS send_message unexpected error: {exc}") from exc
