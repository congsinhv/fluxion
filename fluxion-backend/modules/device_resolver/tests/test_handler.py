"""Unit tests for handler.py — mocks auth + db, tests dispatch and error paths."""

from __future__ import annotations

import datetime as dt_mod
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from exceptions import NotFoundError
from handler import _row_to_device, _row_to_milestone, lambda_handler
from schema_types import DeviceConnectionResponse, DeviceResponse, MilestoneConnectionResponse

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SCHEMA = "dev1"
DEVICE_ID = str(uuid.uuid4())
DI_ID = str(uuid.uuid4())

_CONTEXT = MagicMock()
_CONTEXT.aws_request_id = "test-req-id"

_CLAIMS: dict[str, Any] = {
    "sub": "cognito-sub-123",
    "custom:tenant_id": "1",
}

_EVENT_BASE: dict[str, Any] = {
    "identity": {"claims": _CLAIMS},
    "info": {"fieldName": "getDevice"},
    "arguments": {"id": DEVICE_ID},
}

_MOCK_CTX = MagicMock()
_MOCK_CTX.cognito_sub = "cognito-sub-123"
_MOCK_CTX.user_id = 42
_MOCK_CTX.tenant_id = 1
_MOCK_CTX.tenant_schema = SCHEMA

_DEVICE_RESPONSE = DeviceResponse(
    id=DEVICE_ID,
    createdAt="2026-01-01T00:00:00+00:00",
    updatedAt="2026-01-01T00:00:00+00:00",
    information=None,
)

_DEVICE_CONNECTION = DeviceConnectionResponse(
    items=[_DEVICE_RESPONSE],
    nextToken=None,
    totalCount=1,
)

_MILESTONE_CONNECTION = MilestoneConnectionResponse(items=[], nextToken=None)


def _event(field: str, args: dict[str, Any]) -> dict[str, Any]:
    return {**_EVENT_BASE, "info": {"fieldName": field}, "arguments": args}


# ---------------------------------------------------------------------------
# Unknown field
# ---------------------------------------------------------------------------


def test_unknown_field_returns_error() -> None:
    event = _event("nonExistentField", {})
    result = lambda_handler(event, _CONTEXT)
    assert result["errorType"] == "UNKNOWN_FIELD"


# ---------------------------------------------------------------------------
# getDevice — happy path
# ---------------------------------------------------------------------------


def test_get_device_happy_path() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
        patch("handler.Database") as MockDB,
    ):
        # auth.permission_required uses auth.Database for permission check
        mock_auth_db = MockAuthDB.return_value.__enter__.return_value
        mock_auth_db.has_permission.return_value = True
        # handler.get_device uses handler.Database for data query
        mock_db = MockDB.return_value.__enter__.return_value
        mock_db.get_device_by_id.return_value = {
            "id": DEVICE_ID,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "di_id": None,
        }
        event = _event("getDevice", {"id": DEVICE_ID})
        result = lambda_handler(event, _CONTEXT)

    assert result["id"] == DEVICE_ID
    assert "errorType" not in result


# ---------------------------------------------------------------------------
# getDevice — not found
# ---------------------------------------------------------------------------


def test_get_device_not_found() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
        patch("handler.Database") as MockDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.get_device_by_id.side_effect = NotFoundError(
            "device not found"
        )
        event = _event("getDevice", {"id": DEVICE_ID})
        result = lambda_handler(event, _CONTEXT)

    assert result["errorType"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# getDevice — permission denied
# ---------------------------------------------------------------------------


def test_get_device_permission_denied() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = False
        event = _event("getDevice", {"id": DEVICE_ID})
        result = lambda_handler(event, _CONTEXT)

    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# listDevices — happy path
# ---------------------------------------------------------------------------


def test_list_devices_happy_path() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
        patch("handler.Database") as MockDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.list_devices.return_value = (
            [
                {
                    "id": DEVICE_ID,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "di_id": None,
                }
            ],
            None,
        )
        event = _event("listDevices", {"limit": 10})
        result = lambda_handler(event, _CONTEXT)

    assert "items" in result
    assert result["nextToken"] is None
    assert "errorType" not in result


# ---------------------------------------------------------------------------
# listDevices — with filter
# ---------------------------------------------------------------------------


def test_list_devices_with_filter() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
        patch("handler.Database") as MockDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        mock_data_db = MockDB.return_value.__enter__.return_value
        mock_data_db.list_devices.return_value = ([], None)
        event = _event("listDevices", {"filter": {"stateId": 4}, "limit": 5})
        result = lambda_handler(event, _CONTEXT)

    assert result["items"] == []
    mock_data_db.list_devices.assert_called_once_with(
        limit=5, after_id=None, state_id=4, policy_id=None, search=None
    )


# ---------------------------------------------------------------------------
# getDeviceHistory — happy path
# ---------------------------------------------------------------------------


def test_get_device_history_happy_path() -> None:
    milestone_id = str(uuid.uuid4())
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
        patch("handler.Database") as MockDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = True
        MockDB.return_value.__enter__.return_value.get_device_history.return_value = (
            [
                {
                    "id": milestone_id,
                    "device_id": DEVICE_ID,
                    "assigned_action_id": None,
                    "policy_id": 4,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "ext_fields": None,
                }
            ],
            None,
        )
        event = _event("getDeviceHistory", {"deviceId": DEVICE_ID, "limit": 20})
        result = lambda_handler(event, _CONTEXT)

    assert "items" in result
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == milestone_id


# ---------------------------------------------------------------------------
# getDeviceHistory — permission denied
# ---------------------------------------------------------------------------


def test_get_device_history_permission_denied() -> None:
    with (
        patch("auth.build_context_from", return_value=_MOCK_CTX),
        patch("auth.Database") as MockAuthDB,
    ):
        MockAuthDB.return_value.__enter__.return_value.has_permission.return_value = False
        event = _event("getDeviceHistory", {"deviceId": DEVICE_ID})
        result = lambda_handler(event, _CONTEXT)

    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Missing identity claims
# ---------------------------------------------------------------------------


def test_missing_identity_returns_unauthenticated() -> None:
    event = {
        "identity": {},  # no claims
        "info": {"fieldName": "getDevice"},
        "arguments": {"id": DEVICE_ID},
    }
    result = lambda_handler(event, _CONTEXT)
    assert result["errorType"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
# exceptions.py coverage: to_appsync_error on each subclass
# ---------------------------------------------------------------------------


def test_exception_to_appsync_error_shapes() -> None:
    from exceptions import (
        AuthenticationError,
        DatabaseError,
        ForbiddenError,
        InvalidInputError,
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


# ---------------------------------------------------------------------------
# AWSDateTime: datetime objects must serialise with T separator (not space)
# ---------------------------------------------------------------------------


def test_row_to_device_datetime_iso_separator() -> None:
    """psycopg3 returns real datetime objects; AppSync AWSDateTime requires ISO-8601 with T."""
    dt = datetime(2026, 3, 15, 12, 30, 45, tzinfo=dt_mod.UTC)
    row = {
        "id": DEVICE_ID,
        "created_at": dt,
        "updated_at": dt,
        "di_id": None,
    }
    result = _row_to_device(row)
    assert "T" in result.createdAt, f"expected T separator, got: {result.createdAt!r}"
    assert "T" in result.updatedAt, f"expected T separator, got: {result.updatedAt!r}"
    assert " " not in result.createdAt


def test_row_to_device_last_checkin_iso_separator() -> None:
    dt = datetime(2026, 3, 15, 12, 30, 45, tzinfo=dt_mod.UTC)
    row = {
        "id": DEVICE_ID,
        "created_at": dt,
        "updated_at": dt,
        "di_id": DI_ID,
        "serial_number": "SN123",
        "udid": "UDID-ABC",
        "di_name": "Test Device",
        "model": "iPhone 15",
        "os_version": "17.0",
        "battery_level": 85,
        "wifi_mac": "AA:BB:CC:DD:EE:FF",
        "is_supervised": True,
        "last_checkin_at": dt,
        "ext_fields": None,
    }
    result = _row_to_device(row)
    assert result.information is not None
    assert result.information.lastCheckinAt is not None
    assert "T" in result.information.lastCheckinAt


def test_row_to_milestone_iso_separator() -> None:
    dt = datetime(2026, 3, 15, 12, 30, 45, tzinfo=dt_mod.UTC)
    row = {
        "id": str(uuid.uuid4()),
        "device_id": DEVICE_ID,
        "assigned_action_id": None,
        "policy_id": 1,
        "created_at": dt,
        "ext_fields": None,
    }
    result = _row_to_milestone(row)
    assert "T" in result.createdAt, f"expected T separator, got: {result.createdAt!r}"
    assert " " not in result.createdAt
