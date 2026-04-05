"""Tests for user_resolver handler — mock DBConnection + Cognito, test resolver logic."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

with patch.dict("os.environ", {
    "POWERTOOLS_SERVICE_NAME": "test",
    "POWERTOOLS_TRACE_DISABLED": "1",
    "COGNITO_USER_POOL_ID": "us-east-1_TestPool",
    "AWS_DEFAULT_REGION": "ap-southeast-1",
}):
    from db import DBConnection
    from handler import app

TENANT = "test_tenant"
NOW = datetime(2026, 1, 1, tzinfo=UTC)

MOCK_USER_ROW = {
    "id": "u-001",
    "email": "admin@test.com",
    "name": "Test Admin",
    "role": "admin",
    "is_active": True,
    "cognito_sub": "cognito-sub-001",
    "created_at": NOW,
    "updated_at": NOW,
}


def _make_event(field_name: str, arguments: dict, type_name: str = "Query", role: str = "ADMIN") -> dict:
    return {
        "typeName": type_name,
        "fieldName": field_name,
        "arguments": arguments,
        "identity": {
            "claims": {"custom:tenant_id": TENANT, "custom:role": role, "sub": "cognito-sub-001"},
            "sub": "cognito-sub-001",
        },
        "info": {"fieldName": field_name, "parentTypeName": type_name, "selectionSetList": []},
    }


# ─── Queries ─────────────────────────────────────────────────────────────────────


class TestMe:
    @patch.object(DBConnection, "get_user_by_cognito_sub")
    def test_returns_current_user(self, mock_get):
        mock_get.return_value = MOCK_USER_ROW
        result = app.resolve(_make_event("me", {}), MagicMock())

        assert result["id"] == "u-001"
        assert result["email"] == "admin@test.com"
        assert result["role"] == "ADMIN"  # uppercased by format_user
        mock_get.assert_called_once_with(schema_name=TENANT, cognito_sub="cognito-sub-001")

    @patch.object(DBConnection, "get_user_by_cognito_sub")
    def test_raises_not_found(self, mock_get):
        mock_get.return_value = None
        with pytest.raises(Exception, match="not found"):
            app.resolve(_make_event("me", {}), MagicMock())


class TestGetUser:
    @patch.object(DBConnection, "get_user_by_id")
    def test_returns_user(self, mock_get):
        mock_get.return_value = MOCK_USER_ROW
        result = app.resolve(_make_event("getUser", {"id": "u-001"}), MagicMock())

        assert result["id"] == "u-001"
        assert result["name"] == "Test Admin"

    @patch.object(DBConnection, "get_user_by_id")
    def test_raises_not_found(self, mock_get):
        mock_get.return_value = None
        with pytest.raises(Exception, match="not found"):
            app.resolve(_make_event("getUser", {"id": "nonexistent"}), MagicMock())


class TestListUsers:
    @patch.object(DBConnection, "count_users")
    @patch.object(DBConnection, "list_users")
    def test_returns_paginated_list(self, mock_list, mock_count):
        mock_list.return_value = [MOCK_USER_ROW]
        mock_count.return_value = 1
        result = app.resolve(_make_event("listUsers", {"limit": 20}), MagicMock())

        assert len(result["items"]) == 1
        assert result["nextToken"] is None
        assert result["totalCount"] == 1

    @patch.object(DBConnection, "count_users")
    @patch.object(DBConnection, "list_users")
    def test_limit_capped(self, mock_list, mock_count):
        mock_list.return_value = []
        mock_count.return_value = 0
        app.resolve(_make_event("listUsers", {"limit": 9999}), MagicMock())

        call_args = mock_list.call_args
        assert call_args.kwargs["limit"] == 100


# ─── Mutations ───────────────────────────────────────────────────────────────────


class TestCreateUser:
    @patch.object(DBConnection, "create_user")
    @patch("handler.cognito_client")
    def test_creates_cognito_and_db_user(self, mock_cognito, mock_create):
        mock_cognito.admin_create_user.return_value = {
            "User": {
                "Username": "new@test.com",
                "Attributes": [
                    {"Name": "sub", "Value": "new-sub-123"},
                    {"Name": "email", "Value": "new@test.com"},
                ],
            }
        }
        mock_create.return_value = {
            "id": "u-002", "email": "new@test.com", "name": "New User",
            "role": "operator", "is_active": True, "created_at": NOW, "updated_at": NOW,
        }
        result = app.resolve(
            _make_event(
                "createUser",
                {"input": {"email": "new@test.com", "name": "New User", "role": "OPERATOR"}},
                type_name="Mutation",
            ),
            MagicMock(),
        )

        assert result["id"] == "u-002"
        assert result["email"] == "new@test.com"
        # Verify Cognito sub extracted from Attributes, not Username
        mock_create.assert_called_once_with(
            schema_name=TENANT, email="new@test.com", name="New User",
            role="OPERATOR", cognito_sub="new-sub-123",
        )

    def test_forbidden_for_operator(self):
        with pytest.raises(Exception, match="ADMIN"):
            app.resolve(
                _make_event(
                    "createUser",
                    {"input": {"email": "x@x.com", "name": "X", "role": "OPERATOR"}},
                    type_name="Mutation",
                    role="OPERATOR",
                ),
                MagicMock(),
            )


class TestUpdateUser:
    @patch("handler.cognito_client")
    @patch.object(DBConnection, "update_user")
    def test_updates_user_and_syncs_role(self, mock_update, mock_cognito):
        mock_update.return_value = {
            **MOCK_USER_ROW,
            "role": "operator",
            "cognito_sub": "cognito-sub-001",
        }
        result = app.resolve(
            _make_event("updateUser", {"id": "u-001", "input": {"role": "OPERATOR"}}, type_name="Mutation"),
            MagicMock(),
        )

        assert result["role"] == "OPERATOR"
        # Verify Cognito role sync was called
        mock_cognito.admin_update_user_attributes.assert_called_once()

    @patch.object(DBConnection, "update_user")
    def test_raises_not_found(self, mock_update):
        mock_update.return_value = None
        with pytest.raises(Exception, match="not found"):
            app.resolve(
                _make_event("updateUser", {"id": "nonexistent", "input": {"name": "X"}}, type_name="Mutation"),
                MagicMock(),
            )

    def test_forbidden_for_operator(self):
        with pytest.raises(Exception, match="ADMIN"):
            app.resolve(
                _make_event(
                    "updateUser", {"id": "u-001", "input": {"name": "X"}},
                    type_name="Mutation", role="OPERATOR",
                ),
                MagicMock(),
            )
