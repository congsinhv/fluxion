"""Tests for checkin_handler — mock DB + AppSync, test all 4 event types."""

import json
from unittest.mock import MagicMock, patch

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict(
    "os.environ",
    {
        "POWERTOOLS_SERVICE_NAME": "test",
        "POWERTOOLS_TRACE_DISABLED": "1",
        "APPSYNC_ENDPOINT": "https://test.appsync-api.ap-southeast-1.amazonaws.com/graphql",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
    },
):
    from db import DBConnection
    from handler import handler


def _make_sqs_event(records: list[dict]) -> dict:
    return {
        "Records": [
            {"messageId": f"msg-{i}", "body": json.dumps(rec)}
            for i, rec in enumerate(records)
        ],
    }


def _checkin_msg(event_type: str, device_id: str = "d-001", payload: dict | None = None) -> dict:
    return {
        "eventType": event_type,
        "tenantId": "test_tenant",
        "deviceId": device_id,
        "payload": payload or {},
    }


MOCK_EXECUTION = {"id": "exec-001", "device_id": "d-001", "action_id": "a-001"}
MOCK_POLICY = {"apply_policy_id": 3, "state_id": 3}


# --- DEVICE_TOKEN_UPDATE ---

class TestTokenUpdate:
    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "update_device_token")
    def test_happy_path(self, mock_upsert, mock_appsync):
        payload = {"pushToken": "abcdef", "pushMagic": "magic-1", "topic": "com.apple.mgmt", "unlockToken": None}
        event = _make_sqs_event([_checkin_msg("DEVICE_TOKEN_UPDATE", payload=payload)])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args.kwargs
        assert call_kwargs["push_token"] == bytes.fromhex("abcdef")
        assert call_kwargs["push_magic"] == "magic-1"
        mock_appsync.assert_not_called()


# --- DEVICE_RELEASED ---

class TestDeviceReleased:
    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "update_device")
    def test_happy_path(self, mock_update, mock_appsync):
        event = _make_sqs_event([_checkin_msg("DEVICE_RELEASED", payload={"udid": "UD-001"})])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_update.assert_called_once_with(
            "test_tenant", "d-001", state_id=6, current_policy_id=6, assigned_action_id=None,
        )
        mock_appsync.assert_called_once()
        variables = mock_appsync.call_args[0][1]
        assert variables["deviceId"] == "d-001"
        assert variables["stateId"] == 6
        assert variables["currentPolicyId"] == 6


# --- ACTION_COMPLETED ---

class TestActionCompleted:
    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "insert_milestone")
    @patch.object(DBConnection, "update_device")
    @patch.object(DBConnection, "get_action_policy")
    @patch.object(DBConnection, "update_action_execution")
    def test_happy_path(self, mock_exec, mock_policy, mock_device, mock_milestone, mock_appsync):
        mock_exec.return_value = MOCK_EXECUTION
        mock_policy.return_value = MOCK_POLICY

        payload = {"commandUuid": "cmd-001", "resultPayload": None}
        event = _make_sqs_event([_checkin_msg("ACTION_COMPLETED", payload=payload)])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_exec.assert_called_once_with("test_tenant", "cmd-001", "ACTION_COMPLETED")
        mock_policy.assert_called_once_with("test_tenant", "a-001")
        mock_device.assert_called_once_with(
            "test_tenant", "d-001", state_id=3, current_policy_id=3, assigned_action_id=None,
        )
        mock_milestone.assert_called_once_with("test_tenant", "d-001", "a-001", 3)
        assert mock_appsync.call_count == 2

    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "get_action_policy")
    @patch.object(DBConnection, "update_action_execution")
    def test_appsync_variables(self, mock_exec, mock_policy, mock_appsync):
        """Verify correct variables passed to AppSync mutations."""
        mock_exec.return_value = MOCK_EXECUTION
        mock_policy.return_value = MOCK_POLICY

        payload = {"commandUuid": "cmd-001"}
        event = _make_sqs_event([_checkin_msg("ACTION_COMPLETED", payload=payload)])
        with patch.object(DBConnection, "update_device"), patch.object(DBConnection, "insert_milestone"):
            handler(event, MagicMock())

        # First call: notifyActionExecutionUpdated (fires early, before policy lookup)
        exec_vars = mock_appsync.call_args_list[0][0][1]
        assert exec_vars["executionId"] == "exec-001"
        assert exec_vars["status"] == "ACTION_COMPLETED"
        # Second call: notifyDeviceStateChanged
        state_vars = mock_appsync.call_args_list[1][0][1]
        assert state_vars["stateId"] == 3
        assert state_vars["currentPolicyId"] == 3

    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "update_action_execution")
    def test_execution_not_found(self, mock_exec, mock_appsync):
        mock_exec.return_value = None

        payload = {"commandUuid": "unknown-cmd"}
        event = _make_sqs_event([_checkin_msg("ACTION_COMPLETED", payload=payload)])
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        mock_appsync.assert_not_called()


# --- ACTION_FAILED ---

class TestActionFailed:
    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "update_device")
    @patch.object(DBConnection, "update_action_execution")
    def test_happy_path(self, mock_exec, mock_device, mock_appsync):
        mock_exec.return_value = MOCK_EXECUTION

        payload = {"commandUuid": "cmd-001", "errorMessage": "Device unreachable"}
        event = _make_sqs_event([_checkin_msg("ACTION_FAILED", payload=payload)])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_exec.assert_called_once_with("test_tenant", "cmd-001", "ACTION_FAILED")
        mock_device.assert_called_once_with("test_tenant", "d-001", assigned_action_id=None)
        # Only notifyActionExecutionUpdated (not device state)
        mock_appsync.assert_called_once()
        variables = mock_appsync.call_args[0][1]
        assert variables["status"] == "ACTION_FAILED"


# --- General ---

class TestGeneral:
    def test_unknown_event_type(self):
        event = _make_sqs_event([_checkin_msg("UNKNOWN_EVENT")])
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1

    @patch("handler.call_appsync_mutation")
    @patch.object(DBConnection, "update_device")
    @patch.object(DBConnection, "update_device_token")
    def test_mixed_records_partial_failure(self, mock_token, mock_device, mock_appsync):
        """3 records: token update OK, unknown type fails, release OK."""
        records = [
            _checkin_msg("DEVICE_TOKEN_UPDATE", device_id="d-001", payload={
                "pushToken": "aa", "pushMagic": "m", "topic": "t", "unlockToken": None,
            }),
            _checkin_msg("INVALID_TYPE", device_id="d-002"),
            _checkin_msg("DEVICE_RELEASED", device_id="d-003", payload={"udid": "UD-3"}),
        ]
        event = _make_sqs_event(records)
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-1"
        mock_token.assert_called_once()
        mock_device.assert_called_once()
