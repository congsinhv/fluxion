"""Tests for device_resolver handler — mock DBConnection, test resolver logic."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict("os.environ", {"POWERTOOLS_SERVICE_NAME": "test", "POWERTOOLS_TRACE_DISABLED": "1"}):
    from db import DBConnection
    from handler import app


TENANT = "test_tenant"
NOW = datetime(2026, 1, 1, tzinfo=UTC)

MOCK_DEVICE_ROW = {
    "id": "d-001",
    "state_id": 1,
    "current_policy_id": 2,
    "assigned_action_id": None,
    "created_at": NOW,
    "updated_at": NOW,
    "state_name": "Enrolled",
    "policy_name": "Default Policy",
    "policy_state_id": 1,
    "policy_service_type_id": 1,
    "policy_color": "00FF00",
    "info_id": "i-001",
    "serial_number": "SN123",
    "udid": "UDID123",
    "device_name": "iPhone 15",
    "model": "iPhone15,2",
    "os_version": "17.0",
    "battery_level": 0.85,
    "wifi_mac": "AA:BB:CC:DD",
    "is_supervised": True,
    "last_checkin_at": NOW,
    "info_ext_fields": None,
    "token_id": "t-001",
    "topic": "com.apple.mgmt",
    "token_updated_at": NOW,
}


def _make_appsync_event(field_name: str, arguments: dict, type_name: str = "Query") -> dict:
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


class TestGetDevice:
    @patch.object(DBConnection, "get_device_by_id")
    def test_returns_formatted_device(self, mock_get):
        mock_get.return_value = MOCK_DEVICE_ROW
        event = _make_appsync_event("getDevice", {"id": "d-001"})
        result = app.resolve(event, MagicMock())

        assert result["id"] == "d-001"
        assert result["stateId"] == 1
        assert result["state"]["name"] == "Enrolled"
        assert result["information"]["serialNumber"] == "SN123"
        assert result["tokens"]["topic"] == "com.apple.mgmt"
        mock_get.assert_called_once_with(schema_name=TENANT, device_id="d-001")

    @patch.object(DBConnection, "get_device_by_id")
    def test_raises_not_found(self, mock_get):
        mock_get.return_value = None
        event = _make_appsync_event("getDevice", {"id": "nonexistent"})

        with pytest.raises(Exception, match="not found"):
            app.resolve(event, MagicMock())


class TestListDevices:
    @patch.object(DBConnection, "count_devices")
    @patch.object(DBConnection, "list_devices")
    def test_returns_paginated_list(self, mock_list, mock_count):
        mock_list.return_value = [MOCK_DEVICE_ROW]  # 1 row, no hasMore
        mock_count.return_value = 1
        event = _make_appsync_event("listDevices", {"limit": 20})
        result = app.resolve(event, MagicMock())

        assert len(result["items"]) == 1
        assert result["nextToken"] is None
        assert result["totalCount"] == 1

    @patch.object(DBConnection, "count_devices")
    @patch.object(DBConnection, "list_devices")
    def test_has_next_page(self, mock_list, mock_count):
        # Return limit+1 rows to indicate more pages
        rows = [MOCK_DEVICE_ROW] * 3
        mock_list.return_value = rows
        mock_count.return_value = 10
        event = _make_appsync_event("listDevices", {"limit": 2})
        result = app.resolve(event, MagicMock())

        assert len(result["items"]) == 2
        assert result["nextToken"] is not None
        assert result["totalCount"] == 10

    @patch.object(DBConnection, "count_devices")
    @patch.object(DBConnection, "list_devices")
    def test_limit_capped_at_max(self, mock_list, mock_count):
        mock_list.return_value = []
        mock_count.return_value = 0
        event = _make_appsync_event("listDevices", {"limit": 9999})
        app.resolve(event, MagicMock())

        # Verify limit passed to DB is capped at MAX_LIMIT (100)
        call_args = mock_list.call_args
        assert call_args.kwargs["limit"] == 100


class TestGetDeviceHistory:
    @patch.object(DBConnection, "get_device_history")
    def test_returns_milestones(self, mock_history):
        milestone_row = {
            "id": "m-001",
            "device_id": "d-001",
            "assigned_action_id": None,
            "policy_id": 2,
            "created_at": NOW,
            "ext_fields": None,
            "action_name": None,
            "action_type_id": None,
            "policy_name": "Default",
            "policy_state_id": 1,
            "policy_color": "00FF00",
        }
        mock_history.return_value = ([milestone_row], 1)
        event = _make_appsync_event("getDeviceHistory", {"deviceId": "d-001"})
        result = app.resolve(event, MagicMock())

        assert len(result["items"]) == 1
        assert result["items"][0]["deviceId"] == "d-001"


class TestListAvailableActions:
    @patch.object(DBConnection, "list_available_actions")
    @patch.object(DBConnection, "get_device_by_id")
    def test_returns_actions_for_device_state(self, mock_get, mock_actions):
        mock_get.return_value = {"state_id": 1, "id": "d-001"}
        action_row = {
            "id": "a-001",
            "name": "Lock",
            "action_type_id": 1,
            "from_state_id": 1,
            "service_type_id": 1,
            "apply_policy_id": 3,
            "configuration": None,
            "policy_name": "Locked",
            "policy_state_id": 2,
            "policy_color": "FF0000",
        }
        mock_actions.return_value = [action_row]
        event = _make_appsync_event("listAvailableActions", {"deviceId": "d-001"})
        result = app.resolve(event, MagicMock())

        assert len(result) == 1
        assert result[0]["name"] == "Lock"
        mock_actions.assert_called_once_with(schema_name=TENANT, device_state_id=1)

    @patch.object(DBConnection, "get_device_by_id")
    def test_raises_not_found_for_missing_device(self, mock_get):
        mock_get.return_value = None
        event = _make_appsync_event("listAvailableActions", {"deviceId": "nonexistent"})

        with pytest.raises(Exception, match="not found"):
            app.resolve(event, MagicMock())
