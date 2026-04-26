"""Unit tests for upload_resolver sqs.py.

All tests patch sqs._get_client to avoid real boto3 calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import sqs as sqs_module
from exceptions import SqsError
from sqs import enqueue_upload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sqs_client(message_id: str = "msg-001") -> MagicMock:
    client = MagicMock()
    client.send_message.return_value = {"MessageId": message_id}
    return client


# ---------------------------------------------------------------------------
# enqueue_upload — happy path
# ---------------------------------------------------------------------------


class TestEnqueueUpload:
    def test_happy_path_returns_message_id(self) -> None:
        client = _make_sqs_client("msg-xyz")
        with patch.object(sqs_module, "_get_client", return_value=client):
            result = enqueue_upload(
                {"tenant_schema": "dev1", "serialNumber": "SN001", "udid": "U001"},
                queue_url="https://sqs.us-east-1.amazonaws.com/000/test",
            )
        assert result == "msg-xyz"

    def test_uses_env_queue_url_when_not_provided(self) -> None:
        client = _make_sqs_client("msg-env")
        with patch.object(sqs_module, "_get_client", return_value=client):
            result = enqueue_upload({"serialNumber": "SN001", "udid": "U001"})
        assert result == "msg-env"
        call_kwargs = client.send_message.call_args[1]
        # Uses the default from UPLOAD_PROCESSOR_QUEUE_URL env (set in conftest).
        assert "QueueUrl" in call_kwargs

    def test_message_body_is_json_serialized(self) -> None:
        client = _make_sqs_client()
        payload = {"tenant_schema": "dev1", "serialNumber": "SN001", "udid": "U001", "name": None}
        with patch.object(sqs_module, "_get_client", return_value=client):
            enqueue_upload(payload, queue_url="https://sqs.test/queue")
        import json

        sent_body = client.send_message.call_args[1]["MessageBody"]
        assert json.loads(sent_body) == payload

    def test_client_error_raises_sqs_error(self) -> None:
        """boto3 ClientError must be converted to SqsError."""
        from botocore.exceptions import ClientError

        client = MagicMock()
        client.send_message.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "SendMessage"
        )
        with patch.object(sqs_module, "_get_client", return_value=client):
            with pytest.raises(SqsError, match="SQS send_message failed"):
                enqueue_upload({"serialNumber": "SN1"}, queue_url="https://sqs.test/q")

    def test_unexpected_error_raises_sqs_error(self) -> None:
        """Non-ClientError exceptions are also wrapped in SqsError."""
        client = MagicMock()
        client.send_message.side_effect = RuntimeError("network failure")
        with patch.object(sqs_module, "_get_client", return_value=client):
            with pytest.raises(SqsError, match="unexpected error"):
                enqueue_upload({"serialNumber": "SN1"}, queue_url="https://sqs.test/q")


# ---------------------------------------------------------------------------
# _get_client — lazy singleton
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_singleton_reused(self) -> None:
        """_get_client returns same instance on second call."""
        sqs_module._client = None  # reset
        mock_boto3 = MagicMock()
        fake_client = MagicMock()
        mock_boto3.client.return_value = fake_client
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            import importlib

            importlib.reload(sqs_module)
            c1 = sqs_module._get_client()
            c2 = sqs_module._get_client()
        assert c1 is c2
        # Reset for other tests.
        sqs_module._client = None
