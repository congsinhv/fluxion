"""Tests for platform_resolver handler — mock DBConnection, test resolver logic."""

from unittest.mock import MagicMock, patch

import pytest

with patch.dict("os.environ", {"POWERTOOLS_SERVICE_NAME": "test", "POWERTOOLS_TRACE_DISABLED": "1"}):
    from db import DBConnection
    from handler import app

TENANT = "test_tenant"


def _make_event(field_name: str, arguments: dict, type_name: str = "Query", role: str = "ADMIN") -> dict:
    return {
        "typeName": type_name,
        "fieldName": field_name,
        "arguments": arguments,
        "identity": {
            "claims": {"custom:tenant_id": TENANT, "custom:role": role, "sub": "sub-123"},
            "sub": "sub-123",
        },
        "info": {"fieldName": field_name, "parentTypeName": type_name, "selectionSetList": []},
    }


# ─── Config queries ──────────────────────────────────────────────────────────────


class TestListStates:
    @patch.object(DBConnection, "list_states")
    def test_returns_states(self, mock_list):
        mock_list.return_value = [{"id": 1, "name": "Enrolled"}, {"id": 2, "name": "Locked"}]
        result = app.resolve(_make_event("listStates", {}), MagicMock())

        assert len(result) == 2
        assert result[0] == {"id": 1, "name": "Enrolled"}
        mock_list.assert_called_once_with(schema_name=TENANT)


class TestListPolicies:
    @patch.object(DBConnection, "list_policies")
    def test_returns_policies_with_state(self, mock_list):
        mock_list.return_value = [{
            "id": 1, "name": "Default", "state_id": 1,
            "service_type_id": 1, "color": "00FF00", "state_name": "Enrolled",
        }]
        result = app.resolve(_make_event("listPolicies", {}), MagicMock())

        assert len(result) == 1
        assert result[0]["stateId"] == 1
        assert result[0]["state"]["name"] == "Enrolled"

    @patch.object(DBConnection, "list_policies")
    def test_filters_by_service_type(self, mock_list):
        mock_list.return_value = []
        app.resolve(_make_event("listPolicies", {"serviceTypeId": 2}), MagicMock())
        mock_list.assert_called_once_with(schema_name=TENANT, service_type_id=2)


class TestListActions:
    @patch.object(DBConnection, "list_actions")
    def test_returns_actions_with_policy(self, mock_list):
        mock_list.return_value = [
            {
                "id": "a-001", "name": "Lock", "action_type_id": 1,
                "from_state_id": 1, "service_type_id": 1, "apply_policy_id": 2,
                "configuration": {"key": "val"},
                "policy_name": "Locked", "policy_state_id": 2, "policy_color": "FF0000",
            }
        ]
        result = app.resolve(_make_event("listActions", {}), MagicMock())

        assert result[0]["name"] == "Lock"
        assert result[0]["applyPolicy"]["name"] == "Locked"
        assert result[0]["configuration"] == '{"key": "val"}'  # json.dumps


class TestListServices:
    @patch.object(DBConnection, "list_services")
    def test_returns_services(self, mock_list):
        mock_list.return_value = [{"id": 1, "name": "MDM", "is_enabled": True}]
        result = app.resolve(_make_event("listServices", {}), MagicMock())

        assert result[0] == {"id": 1, "name": "MDM", "isEnabled": True}


# ─── Config mutations ────────────────────────────────────────────────────────────


class TestUpdateState:
    @patch.object(DBConnection, "update_state")
    def test_updates_state(self, mock_update):
        mock_update.return_value = {"id": 1, "name": "NewName"}
        result = app.resolve(
            _make_event("updateState", {"id": 1, "input": {"name": "NewName"}}, type_name="Mutation"),
            MagicMock(),
        )

        assert result == {"id": 1, "name": "NewName"}
        mock_update.assert_called_once_with(schema_name=TENANT, state_id=1, name="NewName")

    @patch.object(DBConnection, "update_state")
    def test_raises_not_found(self, mock_update):
        mock_update.return_value = None
        with pytest.raises(Exception, match="not found"):
            app.resolve(
                _make_event("updateState", {"id": 999, "input": {"name": "X"}}, type_name="Mutation"),
                MagicMock(),
            )

    def test_forbidden_for_operator(self):
        with pytest.raises(Exception, match="ADMIN"):
            app.resolve(
                _make_event("updateState", {"id": 1, "input": {"name": "X"}}, type_name="Mutation", role="OPERATOR"),
                MagicMock(),
            )


class TestUpdatePolicy:
    @patch.object(DBConnection, "update_policy")
    def test_updates_policy(self, mock_update):
        mock_update.return_value = {"id": 1, "name": "Updated", "state_id": 1, "service_type_id": 1, "color": "0000FF"}
        result = app.resolve(
            _make_event("updatePolicy", {"id": 1, "input": {"name": "Updated"}}, type_name="Mutation"),
            MagicMock(),
        )

        assert result["name"] == "Updated"


class TestUpdateService:
    @patch.object(DBConnection, "update_service")
    def test_updates_service(self, mock_update):
        mock_update.return_value = {"id": 1, "name": "MDM", "is_enabled": False}
        result = app.resolve(
            _make_event("updateService", {"id": 1, "input": {"isEnabled": False}}, type_name="Mutation"),
            MagicMock(),
        )

        assert result["isEnabled"] is False
