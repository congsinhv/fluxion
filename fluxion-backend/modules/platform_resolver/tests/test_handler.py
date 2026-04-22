"""Unit tests for handler.py — mocks auth + db, tests dispatch and error paths."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from exceptions import InvalidInputError, NotFoundError
from handler import (
    _row_to_action,
    _row_to_policy,
    _row_to_service,
    _row_to_state,
    lambda_handler,
)
from schema_types import ActionResponse, PolicyResponse, ServiceResponse, StateResponse

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SCHEMA = "dev1"
ACTION_ID = str(uuid.uuid4())

_CONTEXT = MagicMock()
_CONTEXT.aws_request_id = "test-req-id"

_CLAIMS: dict[str, Any] = {
    "sub": "cognito-sub-123",
    "custom:tenant_id": "1",
}

_EVENT_BASE: dict[str, Any] = {
    "identity": {"claims": _CLAIMS},
    "info": {"fieldName": "listStates"},
    "arguments": {},
}

_MOCK_CTX = MagicMock()
_MOCK_CTX.cognito_sub = "cognito-sub-123"
_MOCK_CTX.user_id = 42
_MOCK_CTX.tenant_id = 1
_MOCK_CTX.tenant_schema = SCHEMA


def _event(field: str, args: dict[str, Any]) -> dict[str, Any]:
    return {**_EVENT_BASE, "info": {"fieldName": field}, "arguments": args}


def _mock_auth_allow() -> tuple[Any, Any]:
    """Return (mock_context_patch, mock_auth_db_patch) both allowing access."""
    ctx_patch = patch("auth.build_context_from", return_value=_MOCK_CTX)
    auth_db_patch = patch("auth.Database")
    return ctx_patch, auth_db_patch


# ---------------------------------------------------------------------------
# Row → response helpers
# ---------------------------------------------------------------------------


def test_row_to_state() -> None:
    row = {"id": 1, "name": "Idle"}
    result = _row_to_state(row)
    assert isinstance(result, StateResponse)
    assert result.id == 1
    assert result.name == "Idle"


def test_row_to_policy() -> None:
    row = {"id": 1, "name": "Idle", "state_id": 1, "service_type_id": 1, "color": None}
    result = _row_to_policy(row)
    assert isinstance(result, PolicyResponse)
    assert result.stateId == 1
    assert result.color is None


def test_row_to_action_with_configuration() -> None:
    row = {
        "id": ACTION_ID,
        "name": "Lock",
        "action_type_id": 5,
        "from_state_id": 4,
        "service_type_id": 3,
        "apply_policy_id": 5,
        "configuration": {"key": "val"},
    }
    result = _row_to_action(row)
    assert isinstance(result, ActionResponse)
    assert result.id == ACTION_ID
    assert result.configuration is not None
    assert "key" in result.configuration


def test_row_to_action_null_optional_fields() -> None:
    row = {
        "id": ACTION_ID,
        "name": "Upload",
        "action_type_id": 1,
        "from_state_id": None,
        "service_type_id": None,
        "apply_policy_id": 1,
        "configuration": None,
    }
    result = _row_to_action(row)
    assert result.fromStateId is None
    assert result.serviceTypeId is None
    assert result.configuration is None


def test_row_to_service() -> None:
    row = {"id": 1, "name": "Inventory", "is_enabled": True}
    result = _row_to_service(row)
    assert isinstance(result, ServiceResponse)
    assert result.isEnabled is True


# ---------------------------------------------------------------------------
# Unknown field
# ---------------------------------------------------------------------------


def test_unknown_field_returns_error() -> None:
    event = _event("nonExistentField", {})
    result = lambda_handler(event, _CONTEXT)
    assert result["errorType"] == "UNKNOWN_FIELD"


# ---------------------------------------------------------------------------
# Missing identity claims
# ---------------------------------------------------------------------------


def test_missing_identity_returns_unauthenticated() -> None:
    event = {
        "identity": {},
        "info": {"fieldName": "listStates"},
        "arguments": {},
    }
    result = lambda_handler(event, _CONTEXT)
    assert result["errorType"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
# listStates — happy path + permission denied
# ---------------------------------------------------------------------------


def test_list_states_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.list_states.return_value = [
            {"id": 1, "name": "Idle"},
            {"id": 2, "name": "Registered"},
        ]
        result = lambda_handler(_event("listStates", {}), _CONTEXT)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert "errorType" not in result[0]


def test_list_states_with_service_type_filter() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        mock_db = MockDB.return_value.__enter__.return_value
        mock_db.list_states.return_value = [{"id": 4, "name": "Active"}]
        result = lambda_handler(_event("listStates", {"serviceTypeId": 3}), _CONTEXT)

    assert len(result) == 1
    mock_db.list_states.assert_called_once_with(service_type_id=3)


def test_list_states_permission_denied() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = False
        result = lambda_handler(_event("listStates", {}), _CONTEXT)
    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# listPolicies — happy path
# ---------------------------------------------------------------------------


def test_list_policies_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.list_policies.return_value = [
            {"id": 4, "name": "Active", "state_id": 4, "service_type_id": 3, "color": None},
        ]
        result = lambda_handler(_event("listPolicies", {"serviceTypeId": 3}), _CONTEXT)

    assert isinstance(result, list)
    assert result[0]["stateId"] == 4


# ---------------------------------------------------------------------------
# listActions — happy path + both filters
# ---------------------------------------------------------------------------


def test_list_actions_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        mock_db = MockDB.return_value.__enter__.return_value
        mock_db.list_actions.return_value = [
            {
                "id": ACTION_ID,
                "name": "Lock",
                "action_type_id": 5,
                "from_state_id": 4,
                "service_type_id": 3,
                "apply_policy_id": 5,
                "configuration": None,
            }
        ]
        result = lambda_handler(
            _event("listActions", {"fromStateId": 4, "serviceTypeId": 3}), _CONTEXT
        )

    assert len(result) == 1
    assert result[0]["id"] == ACTION_ID
    mock_db.list_actions.assert_called_once_with(from_state_id=4, service_type_id=3)


# ---------------------------------------------------------------------------
# listServices — happy path
# ---------------------------------------------------------------------------


def test_list_services_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.list_services.return_value = [
            {"id": 1, "name": "Inventory", "is_enabled": True},
        ]
        result = lambda_handler(_event("listServices", {}), _CONTEXT)

    assert isinstance(result, list)
    assert result[0]["isEnabled"] is True


# ---------------------------------------------------------------------------
# updateState — happy path + non-admin blocked
# ---------------------------------------------------------------------------


def test_update_state_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.update_state.return_value = {
            "id": 1,
            "name": "Idle-renamed",
        }
        result = lambda_handler(
            _event("updateState", {"id": 1, "input": {"name": "Idle-renamed"}}), _CONTEXT
        )

    assert result["name"] == "Idle-renamed"
    assert "errorType" not in result


def test_update_state_missing_name_returns_invalid_input() -> None:
    """ValidationError from missing required field must surface as INVALID_INPUT not 500."""
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        result = lambda_handler(
            _event("updateState", {"id": 1, "input": {}}), _CONTEXT
        )
    assert result["errorType"] == "INVALID_INPUT"


def test_update_state_non_admin_blocked() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = False
        result = lambda_handler(
            _event("updateState", {"id": 1, "input": {"name": "x"}}), _CONTEXT
        )
    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# updatePolicy — empty input raises InvalidInputError
# ---------------------------------------------------------------------------


def test_update_policy_empty_input_invalid() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        result = lambda_handler(
            _event("updatePolicy", {"id": 1, "input": {}}), _CONTEXT
        )
    assert result["errorType"] == "INVALID_INPUT"


def test_update_policy_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.update_policy.return_value = {
            "id": 4,
            "name": "Active-v2",
            "state_id": 4,
            "service_type_id": 3,
            "color": "ff0000",
        }
        result = lambda_handler(
            _event("updatePolicy", {"id": 4, "input": {"name": "Active-v2", "color": "ff0000"}}),
            _CONTEXT,
        )

    assert result["name"] == "Active-v2"
    assert result["color"] == "ff0000"


# ---------------------------------------------------------------------------
# updateAction — patch only specified fields + empty input guard
# ---------------------------------------------------------------------------


def test_update_action_empty_input_invalid() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        result = lambda_handler(
            _event("updateAction", {"id": ACTION_ID, "input": {}}), _CONTEXT
        )
    assert result["errorType"] == "INVALID_INPUT"


def test_update_action_patches_only_specified_fields() -> None:
    """Verify only the supplied field (name) is passed to db.update_action."""
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        mock_db = MockDB.return_value.__enter__.return_value
        mock_db.update_action.return_value = {
            "id": ACTION_ID,
            "name": "Lock-v2",
            "action_type_id": 5,
            "from_state_id": 4,
            "service_type_id": 3,
            "apply_policy_id": 5,
            "configuration": None,
        }
        lambda_handler(
            _event("updateAction", {"id": ACTION_ID, "input": {"name": "Lock-v2"}}), _CONTEXT
        )

    # Only "name" should be passed — not the unset optional fields.
    mock_db.update_action.assert_called_once_with(ACTION_ID, {"name": "Lock-v2"})


# ---------------------------------------------------------------------------
# updateService — empty input guard
# ---------------------------------------------------------------------------


def test_update_service_empty_input_invalid() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        result = lambda_handler(
            _event("updateService", {"id": 1, "input": {}}), _CONTEXT
        )
    assert result["errorType"] == "INVALID_INPUT"


def test_update_service_happy_path() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.update_service.return_value = {
            "id": 2,
            "name": "Supply Chain",
            "is_enabled": True,
        }
        result = lambda_handler(
            _event("updateService", {"id": 2, "input": {"isEnabled": True}}), _CONTEXT
        )

    assert result["isEnabled"] is True


# ---------------------------------------------------------------------------
# updateAction — not found propagates to error response
# ---------------------------------------------------------------------------


def test_update_action_not_found() -> None:
    ctx_p, auth_p = _mock_auth_allow()
    with ctx_p, auth_p as MockAuthDB, patch("handler.Database") as MockDB:
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.update_action.side_effect = NotFoundError(
            f"actions id={ACTION_ID!r}"
        )
        result = lambda_handler(
            _event("updateAction", {"id": ACTION_ID, "input": {"name": "x"}}), _CONTEXT
        )
    assert result["errorType"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# exceptions.py coverage: to_appsync_error on each subclass
# ---------------------------------------------------------------------------


def test_exception_to_appsync_error_shapes() -> None:
    from exceptions import (
        AuthenticationError,
        DatabaseError,
        ForbiddenError,
        NotFoundError,
        TenantNotFoundError,
        UnknownFieldError,
    )

    for cls, expected_code in [
        (DatabaseError, "DATABASE_ERROR"),
        (TenantNotFoundError, "TENANT_NOT_FOUND"),
        (NotFoundError, "NOT_FOUND"),
        (ForbiddenError, "FORBIDDEN"),
        (AuthenticationError, "UNAUTHENTICATED"),
        (InvalidInputError, "INVALID_INPUT"),
        (UnknownFieldError, "UNKNOWN_FIELD"),
    ]:
        exc = cls("test")
        err = exc.to_appsync_error()
        assert err["errorType"] == expected_code
        assert "errorMessage" in err
