"""Tests for action_resolver handler — mock DBConnection + SQS, test FSM validation."""

from unittest.mock import MagicMock, patch

import pytest

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict(
    "os.environ",
    {
        "POWERTOOLS_SERVICE_NAME": "test",
        "POWERTOOLS_TRACE_DISABLED": "1",
        "SQS_QUEUE_URL": "https://sqs.ap-southeast-1.amazonaws.com/123456789/test-queue",
    },
):
    from db import DBConnection
    from handler import app

TENANT = "test_tenant"

MOCK_DEVICE = {
    "id": "d-001",
    "state_id": 1,
    "assigned_action_id": None,
}

MOCK_DEVICE_BUSY = {
    "id": "d-002",
    "state_id": 1,
    "assigned_action_id": "a-existing",
}

MOCK_ACTION = {
    "id": "a-001",
    "name": "Lock",
    "from_state_id": 1,
    "configuration": None,
}

MOCK_ACTION_WRONG_STATE = {
    "id": "a-002",
    "name": "Unlock",
    "from_state_id": 3,
    "configuration": None,
}


def _make_appsync_event(field_name: str, arguments: dict, type_name: str = "Mutation") -> dict:
    """Build a minimal AppSync resolver event."""
    return {
        "typeName": type_name,
        "fieldName": field_name,
        "arguments": arguments,
        "identity": {
            "claims": {
                "custom:tenant_id": TENANT,
                "custom:role": "ADMIN",
                "sub": "cognito-sub-123",
            },
            "sub": "cognito-sub-123",
        },
        "info": {
            "fieldName": field_name,
            "parentTypeName": type_name,
            "selectionSetList": [],
        },
    }


class TestExecuteAction:
    @patch("handler.send_message")
    @patch.object(DBConnection, "get_action_by_id")
    @patch.object(DBConnection, "get_device_for_action")
    def test_happy_path(self, mock_device, mock_action, mock_send):
        mock_device.return_value = MOCK_DEVICE
        mock_action.return_value = MOCK_ACTION
        event = _make_appsync_event(
            "executeAction", {"input": {"deviceId": "d-001", "actionId": "a-001"}}
        )
        result = app.resolve(event, MagicMock())

        assert result["executionId"] is not None
        assert result["commandUuid"] is not None
        assert result["status"] == "ACTION_PENDING"
        mock_send.assert_called_once()

        # Verify SQS payload (second positional arg = body dict)
        call_body = mock_send.call_args[0][1]
        assert call_body["deviceId"] == "d-001"
        assert call_body["actionId"] == "a-001"
        assert call_body["tenantId"] == TENANT
        assert call_body["executionId"] == result["executionId"]
        assert call_body["commandUuid"] == result["commandUuid"]

    @patch("handler.send_message")
    @patch.object(DBConnection, "get_device_for_action")
    def test_device_not_found(self, mock_device, mock_send):
        mock_device.return_value = None
        event = _make_appsync_event(
            "executeAction", {"input": {"deviceId": "nonexistent", "actionId": "a-001"}}
        )

        with pytest.raises(Exception, match="not found"):
            app.resolve(event, MagicMock())
        mock_send.assert_not_called()

    @patch("handler.send_message")
    @patch.object(DBConnection, "get_device_for_action")
    def test_device_busy(self, mock_device, mock_send):
        mock_device.return_value = MOCK_DEVICE_BUSY
        event = _make_appsync_event(
            "executeAction", {"input": {"deviceId": "d-002", "actionId": "a-001"}}
        )

        with pytest.raises(Exception, match="is busy"):
            app.resolve(event, MagicMock())
        mock_send.assert_not_called()

    @patch("handler.send_message")
    @patch.object(DBConnection, "get_action_by_id")
    @patch.object(DBConnection, "get_device_for_action")
    def test_invalid_transition(self, mock_device, mock_action, mock_send):
        mock_device.return_value = MOCK_DEVICE  # state_id=1
        mock_action.return_value = MOCK_ACTION_WRONG_STATE  # from_state_id=3
        event = _make_appsync_event(
            "executeAction", {"input": {"deviceId": "d-001", "actionId": "a-002"}}
        )

        with pytest.raises(Exception, match="Invalid transition"):
            app.resolve(event, MagicMock())
        mock_send.assert_not_called()

    @patch("handler.send_message")
    @patch.object(DBConnection, "get_action_by_id")
    @patch.object(DBConnection, "get_device_for_action")
    def test_action_not_found(self, mock_device, mock_action, mock_send):
        mock_device.return_value = MOCK_DEVICE
        mock_action.return_value = None
        event = _make_appsync_event(
            "executeAction", {"input": {"deviceId": "d-001", "actionId": "nonexistent"}}
        )

        with pytest.raises(Exception, match="not found"):
            app.resolve(event, MagicMock())
        mock_send.assert_not_called()


class TestExecuteBulkAction:
    @patch("handler.send_message")
    @patch.object(DBConnection, "get_action_by_id")
    @patch.object(DBConnection, "get_device_for_action")
    def test_mixed_results(self, mock_device, mock_action, mock_send):
        """2 valid devices + 1 busy device → partial response."""
        mock_device.side_effect = [MOCK_DEVICE, MOCK_DEVICE_BUSY, MOCK_DEVICE]
        mock_action.return_value = MOCK_ACTION
        event = _make_appsync_event(
            "executeBulkAction",
            {"input": {"deviceIds": ["d-001", "d-002", "d-003"], "actionId": "a-001"}},
        )
        result = app.resolve(event, MagicMock())

        assert len(result["valid"]) == 2
        assert len(result["failed"]) == 1
        assert result["failed"][0]["deviceId"] == "d-002"
        assert "busy" in result["failed"][0]["reason"].lower()
        assert mock_send.call_count == 2

    @patch("handler.send_message")
    @patch.object(DBConnection, "get_action_by_id")
    @patch.object(DBConnection, "get_device_for_action")
    def test_all_fail(self, mock_device, mock_action, mock_send):
        """All devices busy → empty valid, all failed."""
        mock_device.return_value = MOCK_DEVICE_BUSY
        mock_action.return_value = MOCK_ACTION
        event = _make_appsync_event(
            "executeBulkAction",
            {"input": {"deviceIds": ["d-001", "d-002"], "actionId": "a-001"}},
        )
        result = app.resolve(event, MagicMock())

        assert len(result["valid"]) == 0
        assert len(result["failed"]) == 2
        mock_send.assert_not_called()
