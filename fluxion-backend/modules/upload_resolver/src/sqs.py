"""Thin boto3 SQS wrapper for upload_resolver.

Sends device-upload messages to the configured SQS queue.
Each message envelope:

    {
      "tenant_schema": <str>,
      "serialNumber":  <str>,
      "udid":          <str>,
      "name":          <str | null>,
      "model":         <str | null>,
      "osVersion":     <str | null>
    }

SQS errors after the dedupe-passed decision are logged but NOT re-raised —
the upload is considered accepted and the consumer is responsible for UNIQUE
violations on the DB side. See handler.py docstring for rationale.
"""

from __future__ import annotations

import json
from typing import Any

from config import UPLOAD_PROCESSOR_QUEUE_URL, logger
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


def enqueue_upload(message_body: dict[str, Any], queue_url: str | None = None) -> str:
    """Send a single device-upload message to SQS.

    Args:
        message_body: Dict conforming to the SQS envelope schema (see module docstring).
        queue_url:    Override queue URL (used in tests); defaults to
                      UPLOAD_PROCESSOR_QUEUE_URL.

    Returns:
        SQS ``MessageId`` string.

    Raises:
        SqsError: boto3 ``ClientError`` or unexpected error from SQS.
    """
    url = queue_url or UPLOAD_PROCESSOR_QUEUE_URL
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
                        "serial_number": message_body.get("serialNumber"),
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
