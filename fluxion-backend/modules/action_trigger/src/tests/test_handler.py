"""Tests for action_trigger handler — mock DB + SNS, test execution creation + command publish."""

import json
from unittest.mock import MagicMock, patch

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict(
    "os.environ",
    {
        "POWERTOOLS_SERVICE_NAME": "test",
        "POWERTOOLS_TRACE_DISABLED": "1",
        "SNS_TOPIC_ARN": "arn:aws:sns:ap-southeast-1:123456789:test-topic",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
    },
):
    from db import DBConnection
    from handler import handler

TENANT = "test_tenant"

MOCK_TOKENS = {
    "push_token": b"\xab\xcd\xef",
    "push_magic": "magic-123",
    "topic": "com.apple.mgmt",
}

MOCK_ACTION = {
    "id": "a-001",
    "name": "Lock",
    "action_type_id": 1,
    "configuration": {"key": "value"},
}


def _make_sqs_event(records: list[dict]) -> dict:
    return {
        "Records": [
            {"messageId": f"msg-{i}", "body": json.dumps(rec)}
            for i, rec in enumerate(records)
        ],
    }


def _action_msg(
    device_id: str = "d-001",
    action_id: str = "a-001",
    execution_id: str = "exec-001",
    command_uuid: str = "cmd-001",
) -> dict:
    return {
        "executionId": execution_id,
        "commandUuid": command_uuid,
        "deviceId": device_id,
        "actionId": action_id,
        "configuration": None,
        "tenantId": TENANT,
    }


class TestActionTrigger:
    @patch("handler.send_sns_message")
    @patch.object(DBConnection, "get_device_udid")
    @patch.object(DBConnection, "get_action_details")
    @patch.object(DBConnection, "get_device_tokens")
    @patch.object(DBConnection, "create_execution_and_assign")
    def test_happy_path(self, mock_create, mock_tokens, mock_action, mock_udid, mock_sns):
        """Record processed → execution created, action assigned, SNS published."""
        mock_tokens.return_value = MOCK_TOKENS
        mock_action.return_value = MOCK_ACTION
        mock_udid.return_value = "UDID-123"

        event = _make_sqs_event([_action_msg()])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_create.assert_called_once_with(TENANT, "exec-001", "cmd-001", "d-001", "a-001")
        mock_sns.assert_called_once()

        # Verify SNS payload
        sns_body = mock_sns.call_args[0][1]
        assert sns_body["commandUuid"] == "cmd-001"
        assert sns_body["deviceUdid"] == "UDID-123"
        assert sns_body["pushToken"] == "abcdef"
        assert sns_body["pushMagic"] == "magic-123"
        assert sns_body["topic"] == "com.apple.mgmt"
        assert sns_body["requestType"] == "Lock"
        assert sns_body["tenantId"] == TENANT

    @patch("handler.send_sns_message")
    @patch.object(DBConnection, "get_device_tokens")
    @patch.object(DBConnection, "create_execution_and_assign")
    def test_device_tokens_not_found(self, mock_create, mock_tokens, mock_sns):
        """No device tokens → error → batch failure."""
        mock_tokens.return_value = None

        event = _make_sqs_event([_action_msg()])
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-0"
        mock_sns.assert_not_called()

    @patch("handler.send_sns_message")
    @patch.object(DBConnection, "get_device_udid")
    @patch.object(DBConnection, "get_action_details")
    @patch.object(DBConnection, "get_device_tokens")
    @patch.object(DBConnection, "create_execution_and_assign")
    def test_multiple_records(self, mock_create, mock_tokens, mock_action, mock_udid, mock_sns):
        """2 records → both processed, SNS called 2x."""
        mock_tokens.return_value = MOCK_TOKENS
        mock_action.return_value = MOCK_ACTION
        mock_udid.return_value = "UDID-123"

        event = _make_sqs_event([
            _action_msg(device_id="d-001", execution_id="exec-1"),
            _action_msg(device_id="d-002", execution_id="exec-2"),
        ])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        assert mock_sns.call_count == 2

    @patch("handler.send_sns_message")
    @patch.object(DBConnection, "get_device_tokens")
    @patch.object(DBConnection, "create_execution_and_assign")
    def test_partial_failure(self, mock_create, mock_tokens, mock_sns):
        """2 records, second has no tokens → 1 batch failure."""
        mock_tokens.side_effect = [MOCK_TOKENS, None]

        # First record needs full mocks for SNS path
        with patch.object(DBConnection, "get_action_details", return_value=MOCK_ACTION), \
             patch.object(DBConnection, "get_device_udid", return_value="UDID-1"):
            event = _make_sqs_event([
                _action_msg(device_id="d-001", execution_id="exec-1"),
                _action_msg(device_id="d-002", execution_id="exec-2"),
            ])
            result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-1"
        assert mock_sns.call_count == 1

    @patch("handler.send_sns_message")
    @patch.object(DBConnection, "get_device_udid")
    @patch.object(DBConnection, "get_action_details")
    @patch.object(DBConnection, "get_device_tokens")
    @patch.object(DBConnection, "create_execution_and_assign")
    def test_configuration_from_message(self, mock_create, mock_tokens, mock_action, mock_udid, mock_sns):
        """Configuration from message body takes priority over action configuration."""
        mock_tokens.return_value = MOCK_TOKENS
        mock_action.return_value = MOCK_ACTION
        mock_udid.return_value = "UDID-123"

        msg = _action_msg()
        msg["configuration"] = '{"custom": "config"}'
        event = _make_sqs_event([msg])
        handler(event, MagicMock())

        sns_body = mock_sns.call_args[0][1]
        assert sns_body["commandPayload"] == '{"custom": "config"}'
