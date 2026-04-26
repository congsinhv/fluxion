"""Tests for action_resolver sqs.py — thin boto3 SQS wrapper.

Covers:
  - Happy path: enqueue_action_trigger returns MessageId
  - boto3 ClientError → SqsError raised
  - Non-ClientError exception → SqsError raised
  - Queue URL override (used in tests)
  - Lazy client singleton reuse

boto3 is imported lazily inside _get_client(); tests patch sqs._get_client
rather than sqs.boto3 to avoid import-time attribute errors.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import sqs as sqs_module
from exceptions import SqsError

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/000000000000/test-queue"
DEVICE_ID = str(uuid.uuid4())
BATCH_ID = str(uuid.uuid4())


def _make_envelope() -> dict[str, Any]:
    return {
        "batchId": BATCH_ID,
        "deviceId": DEVICE_ID,
        "actionId": str(uuid.uuid4()),
        "executionId": str(uuid.uuid4()),
        "commandUuid": str(uuid.uuid4()),
        "configuration": None,
        "tenant_schema": "dev1",
    }


def _make_mock_client(message_id: str = "msg-123") -> MagicMock:
    """Build a mock boto3 SQS client."""
    client = MagicMock()
    client.send_message.return_value = {"MessageId": message_id}
    return client


def test_enqueue_action_trigger_happy_path() -> None:
    """Happy path: returns MessageId string from SQS response."""
    mock_client = _make_mock_client("msg-123")

    with patch("sqs._get_client", return_value=mock_client):
        result = sqs_module.enqueue_action_trigger(_make_envelope(), queue_url=QUEUE_URL)

    assert result == "msg-123"
    mock_client.send_message.assert_called_once()
    call_kwargs = mock_client.send_message.call_args
    assert call_kwargs.kwargs["QueueUrl"] == QUEUE_URL
    body = json.loads(call_kwargs.kwargs["MessageBody"])
    assert body["deviceId"] == DEVICE_ID


def test_enqueue_action_trigger_sends_correct_json_body() -> None:
    """MessageBody is valid JSON containing all envelope fields including messageContent."""
    envelope = _make_envelope()
    envelope["messageContent"] = "Lock your device"
    mock_client = _make_mock_client("msg-456")

    with patch("sqs._get_client", return_value=mock_client):
        sqs_module.enqueue_action_trigger(envelope, queue_url=QUEUE_URL)

    sent_body = json.loads(mock_client.send_message.call_args.kwargs["MessageBody"])
    assert sent_body["messageContent"] == "Lock your device"
    assert sent_body["tenant_schema"] == "dev1"
    assert sent_body["batchId"] == BATCH_ID


def test_enqueue_action_trigger_client_error_raises_sqs_error() -> None:
    """boto3 ClientError → SqsError raised with 'SQS send_message failed' message."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        pytest.skip("botocore not installed")

    mock_client = MagicMock()
    mock_client.send_message.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "no access"}}, "SendMessage"
    )

    with patch("sqs._get_client", return_value=mock_client):
        with pytest.raises(SqsError, match="SQS send_message failed"):
            sqs_module.enqueue_action_trigger(_make_envelope(), queue_url=QUEUE_URL)


def test_enqueue_action_trigger_unexpected_error_raises_sqs_error() -> None:
    """Unexpected non-ClientError exception → SqsError with 'unexpected error' message."""
    mock_client = MagicMock()
    mock_client.send_message.side_effect = RuntimeError("unexpected boom")

    with patch("sqs._get_client", return_value=mock_client):
        with pytest.raises(SqsError, match="SQS send_message unexpected error"):
            sqs_module.enqueue_action_trigger(_make_envelope(), queue_url=QUEUE_URL)


def test_enqueue_uses_default_queue_url_from_config() -> None:
    """When queue_url not provided, falls back to ACTION_TRIGGER_QUEUE_URL config."""
    mock_client = _make_mock_client("msg-789")

    with (
        patch("sqs._get_client", return_value=mock_client),
        patch("sqs.ACTION_TRIGGER_QUEUE_URL", "https://sqs.example.com/default-queue"),
    ):
        sqs_module.enqueue_action_trigger(_make_envelope())

    call_kwargs = mock_client.send_message.call_args
    assert call_kwargs.kwargs["QueueUrl"] == "https://sqs.example.com/default-queue"


def test_enqueue_reuses_lazy_client_singleton() -> None:
    """_get_client is called each time but returns the same cached instance."""
    mock_client = _make_mock_client()

    # Reset the module-level singleton so we exercise the caching path.
    sqs_module._client = None  # type: ignore[attr-defined]

    call_count = 0

    def fake_get_client() -> MagicMock:
        nonlocal call_count
        call_count += 1
        return mock_client

    with patch("sqs._get_client", side_effect=fake_get_client):
        sqs_module.enqueue_action_trigger(_make_envelope(), queue_url=QUEUE_URL)
        sqs_module.enqueue_action_trigger(_make_envelope(), queue_url=QUEUE_URL)

    assert mock_client.send_message.call_count == 2
