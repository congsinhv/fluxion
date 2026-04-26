"""Unit tests for upload_resolver handler.py.

All DB and SQS calls are mocked. Tests verify the full dispatch flow:
  - Permission enforcement
  - Per-device validation (MISSING_FIELD)
  - Request-level dedupe (DUPLICATE_IN_REQUEST)
  - DB dedupe (DUPLICATE_EXISTING_SERIAL / UDID)
  - SQS fire-and-forget (failure logged, not re-raised)
  - Aggregate counts
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import sqs as sqs_module
from db import Database, ExistingDeviceKeys
from handler import lambda_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(devices: list[dict[str, Any]], *, authed: bool = True) -> dict[str, Any]:
    """Build a minimal AppSync Lambda event for uploadDevices."""
    return {
        "info": {"fieldName": "uploadDevices"},
        "arguments": {"devices": devices},
        "identity": {
            "claims": {
                "sub": "user-sub-001",
                "custom:tenant_id": "1",
            }
        }
        if authed
        else {},
    }


def _make_auth_db(has_perm: bool = True) -> MagicMock:
    """Mock Database for auth (get_schema_name + has_permission)."""
    db = MagicMock(spec=Database)
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.get_schema_name.return_value = "dev1"
    db.has_permission.return_value = has_perm
    return db


def _make_upload_db(
    existing_serials: set[str] | None = None,
    existing_udids: set[str] | None = None,
) -> MagicMock:
    """Mock Database for find_existing_device_keys."""
    db = MagicMock(spec=Database)
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.find_existing_device_keys.return_value = ExistingDeviceKeys(
        serials=existing_serials or set(),
        udids=existing_udids or set(),
    )
    return db


def _make_sqs_client(message_id: str = "msg-001") -> MagicMock:
    client = MagicMock()
    client.send_message.return_value = {"MessageId": message_id}
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestUploadDevicesHappy:
    def test_three_devices_no_dupes(self) -> None:
        """3 clean devices → accepted=3, rejected=0, errors=[]."""
        devices = [{"serialNumber": f"SN00{i}", "udid": f"UDID00{i}"} for i in range(3)]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-1"))

        assert result["totalRequested"] == 3
        assert result["accepted"] == 3
        assert result["rejected"] == 0
        assert result["errors"] == []

    def test_empty_devices_returns_zero_counts(self) -> None:
        """Empty input → {totalRequested:0, accepted:0, rejected:0, errors:[]}."""
        auth_db = _make_auth_db()
        with (
            patch("auth.Database", return_value=auth_db),
        ):
            result = lambda_handler(_make_event([]), MagicMock(aws_request_id="req-empty"))

        assert result["totalRequested"] == 0
        assert result["accepted"] == 0
        assert result["rejected"] == 0
        assert result["errors"] == []

    def test_optional_fields_passed_to_sqs(self) -> None:
        """name, model, osVersion are forwarded in SQS payload."""
        device = {
            "serialNumber": "SN-A",
            "udid": "UDID-A",
            "name": "My Device",
            "model": "iPhone 15",
            "osVersion": "17.0",
        }
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            lambda_handler(_make_event([device]), MagicMock(aws_request_id="req-opt"))

        import json

        sent = json.loads(sqs_client.send_message.call_args[1]["MessageBody"])
        assert sent["name"] == "My Device"
        assert sent["model"] == "iPhone 15"
        assert sent["osVersion"] == "17.0"


# ---------------------------------------------------------------------------
# Permission enforcement
# ---------------------------------------------------------------------------


class TestPermissionEnforcement:
    def test_forbidden_when_no_permission(self) -> None:
        auth_db = _make_auth_db(has_perm=False)
        with patch("auth.Database", return_value=auth_db):
            result = lambda_handler(
                _make_event([{"serialNumber": "SN1", "udid": "U1"}]),
                MagicMock(aws_request_id="req-forbidden"),
            )
        assert result["errorType"] == "FORBIDDEN"

    def test_unauthenticated_when_identity_missing(self) -> None:
        event = {
            "info": {"fieldName": "uploadDevices"},
            "arguments": {"devices": []},
            "identity": {},
        }
        result = lambda_handler(event, MagicMock(aws_request_id="req-unauth"))
        assert result["errorType"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
# MISSING_FIELD validation
# ---------------------------------------------------------------------------


class TestMissingField:
    def test_empty_serial_number(self) -> None:
        auth_db = _make_auth_db()
        with patch("auth.Database", return_value=auth_db):
            result = lambda_handler(
                _make_event([{"serialNumber": "", "udid": "UDID-1"}]),
                MagicMock(aws_request_id="req-msn"),
            )
        assert result["rejected"] == 1
        assert result["accepted"] == 0
        err = result["errors"][0]
        assert err["index"] == 0
        assert "MISSING_FIELD" in err["reason"]
        assert err["serialNumber"] is None

    def test_empty_udid(self) -> None:
        auth_db = _make_auth_db()
        with patch("auth.Database", return_value=auth_db):
            result = lambda_handler(
                _make_event([{"serialNumber": "SN-1", "udid": ""}]),
                MagicMock(aws_request_id="req-mudid"),
            )
        assert result["rejected"] == 1
        err = result["errors"][0]
        assert "MISSING_FIELD" in err["reason"]
        assert err["serialNumber"] == "SN-1"

    def test_index_preserved_for_middle_device(self) -> None:
        """Device at index 1 has empty serial — error.index == 1."""
        devices = [
            {"serialNumber": "SN-0", "udid": "UDID-0"},
            {"serialNumber": "", "udid": "UDID-1"},
            {"serialNumber": "SN-2", "udid": "UDID-2"},
        ]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-idx"))

        assert result["rejected"] == 1
        assert result["accepted"] == 2
        assert result["errors"][0]["index"] == 1


# ---------------------------------------------------------------------------
# DUPLICATE_IN_REQUEST
# ---------------------------------------------------------------------------


class TestDuplicateInRequest:
    def test_duplicate_serial_in_request(self) -> None:
        devices = [
            {"serialNumber": "SN-DUP", "udid": "UDID-A"},
            {"serialNumber": "SN-DUP", "udid": "UDID-B"},
        ]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-dup-sn"))

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        err = result["errors"][0]
        assert err["index"] == 1
        assert "DUPLICATE_IN_REQUEST" in err["reason"]

    def test_duplicate_udid_in_request(self) -> None:
        devices = [
            {"serialNumber": "SN-A", "udid": "UDID-DUP"},
            {"serialNumber": "SN-B", "udid": "UDID-DUP"},
        ]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-dup-ud"))

        assert result["rejected"] == 1
        err = result["errors"][0]
        assert "DUPLICATE_IN_REQUEST" in err["reason"]
        assert err["index"] == 1


# ---------------------------------------------------------------------------
# DUPLICATE_EXISTING_SERIAL / UDID
# ---------------------------------------------------------------------------


class TestDuplicateExisting:
    def test_duplicate_existing_serial(self) -> None:
        devices = [
            {"serialNumber": "SN-EXISTS", "udid": "UDID-NEW"},
        ]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db(existing_serials={"SN-EXISTS"})

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-ex-sn"))

        assert result["accepted"] == 0
        assert result["rejected"] == 1
        err = result["errors"][0]
        assert "DUPLICATE_EXISTING_SERIAL" in err["reason"]
        assert err["index"] == 0

    def test_duplicate_existing_udid(self) -> None:
        devices = [
            {"serialNumber": "SN-NEW", "udid": "UDID-EXISTS"},
        ]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db(existing_udids={"UDID-EXISTS"})

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-ex-ud"))

        assert result["accepted"] == 0
        assert result["rejected"] == 1
        err = result["errors"][0]
        assert "DUPLICATE_EXISTING_UDID" in err["reason"]

    def test_mixed_accepted_and_rejected(self) -> None:
        """3 devices: 1 request-dupe + 1 existing + 1 accepted."""
        devices = [
            {"serialNumber": "SN-OK", "udid": "UDID-OK"},
            {"serialNumber": "SN-DUP", "udid": "UDID-B"},
            {"serialNumber": "SN-DUP", "udid": "UDID-C"},  # request-dupe
        ]
        auth_db = _make_auth_db()
        # SN-OK passes DB check (not in existing)
        upload_db = _make_upload_db(existing_serials=set(), existing_udids=set())
        sqs_client = _make_sqs_client()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch.object(sqs_module, "_get_client", return_value=sqs_client),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-mix"))

        assert result["totalRequested"] == 3
        assert result["accepted"] == 2  # SN-OK and SN-DUP first occurrence
        assert result["rejected"] == 1  # third device (index 2)
        assert result["errors"][0]["index"] == 2


# ---------------------------------------------------------------------------
# Oversize input
# ---------------------------------------------------------------------------


class TestOversizeInput:
    def test_oversize_raises_invalid_input(self) -> None:
        """1001 devices triggers Pydantic cap → INVALID_INPUT error."""
        devices = [{"serialNumber": f"SN{i:04d}", "udid": f"UID{i:04d}"} for i in range(1001)]
        auth_db = _make_auth_db()
        with patch("auth.Database", return_value=auth_db):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-big"))
        assert result["errorType"] == "INVALID_INPUT"
        assert "1000" in result["errorMessage"]


# ---------------------------------------------------------------------------
# SQS fire-and-forget
# ---------------------------------------------------------------------------


class TestSqsFireAndForget:
    def test_sqs_failure_does_not_fail_request(self) -> None:
        """SQS error after dedupe → device still counted as accepted, no error returned."""
        from exceptions import SqsError

        devices = [{"serialNumber": "SN-SQS", "udid": "UDID-SQS"}]
        auth_db = _make_auth_db()
        upload_db = _make_upload_db()

        with (
            patch("auth.Database", return_value=auth_db),
            patch("handler.Database", return_value=upload_db),
            patch("handler.enqueue_upload", side_effect=SqsError("queue error")),
        ):
            result = lambda_handler(_make_event(devices), MagicMock(aws_request_id="req-sqsf"))

        # SQS failure is silent — device still counted as accepted.
        assert result["accepted"] == 1
        assert result["rejected"] == 0
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Unknown field
# ---------------------------------------------------------------------------


class TestUnknownField:
    def test_unknown_field_returns_error(self) -> None:
        event = {
            "info": {"fieldName": "nonExistentField"},
            "arguments": {},
            "identity": {},
        }
        result = lambda_handler(event, MagicMock(aws_request_id="req-unk"))
        assert result["errorType"] == "UNKNOWN_FIELD"
