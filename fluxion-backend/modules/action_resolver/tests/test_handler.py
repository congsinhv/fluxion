"""Tests for action_resolver handler.py.

Uses unittest.mock to stub DB and SQS calls — no real infrastructure needed.
Covers:
  - Happy path: assignAction + assignBulkAction
  - Missing action → ActionNotFoundError (whole-request)
  - Archived template → TemplateArchivedError (whole-request)
  - Template not found → TemplateNotFoundError (whole-request)
  - FSM mismatch → INVALID_TRANSITION (per-device for single / in failed[] for bulk)
  - Already-assigned device → DEVICE_BUSY (race-safe path)
  - SQS enqueue failure after DB commit → request still succeeds
  - Permission denied
  - Unknown field → UNKNOWN_FIELD error dict
  - getActionLog: found, not found (null), permission denied
  - listActionLogs: happy path, cursor pagination
  - generateActionLogErrorReport: happy path, empty errors, batch not found
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from handler import lambda_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEVICE_ID = str(uuid.uuid4())
ACTION_ID = str(uuid.uuid4())
TEMPLATE_ID = str(uuid.uuid4())
EXECUTION_ID = str(uuid.uuid4())
COMMAND_UUID = str(uuid.uuid4())
BATCH_ID = str(uuid.uuid4())


def _make_event(
    field: str,
    input_args: dict[str, Any] | None = None,
    cognito_sub: str = "sub-test",
    tenant_id: str = "1",
) -> dict[str, Any]:
    return {
        "info": {"fieldName": field},
        "arguments": {"input": input_args or {}},
        "identity": {"claims": {"sub": cognito_sub, "custom:tenant_id": tenant_id}},
    }


def _make_ctx_mock() -> MagicMock:
    return MagicMock(aws_request_id="test-corr-id")


def _make_auth_db(has_perm: bool = True) -> MagicMock:
    """Auth-phase DB mock (get_schema_name + has_permission)."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_schema_name.return_value = "dev1"
    mock_db.has_permission.return_value = has_perm
    return mock_db


_SENTINEL: dict[
    str, Any
] = {}  # unique sentinel: distinguishes "caller passed None" from "not passed"


def _make_repo_db(
    action_row: dict[str, Any] | None = _SENTINEL,  # type: ignore[assignment]
    template_row: dict[str, Any] | None = None,
    valid_devices: list[Any] | None = None,
    invalid_devices: list[Any] | None = None,
    executions: list[Any] | None = None,
) -> MagicMock:
    """Repo-phase DB mock (load_action, load_message_template, validate_devices, create_batch).

    Pass action_row=None explicitly to simulate a missing action (load_action returns None).
    Omitting action_row uses a default valid action row.
    """
    from db import ExecutionTuple, ValidDevice

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.load_action.return_value = (
        {"id": ACTION_ID, "from_state_id": 4, "name": "Lock"}
        if action_row is _SENTINEL
        else action_row
    )
    mock_db.load_message_template.return_value = template_row
    mock_db.validate_devices_for_action.return_value = (
        valid_devices if valid_devices is not None else [ValidDevice(DEVICE_ID, 4)],
        invalid_devices if invalid_devices is not None else [],
    )
    mock_db.create_batch_with_devices.return_value = (
        executions
        if executions is not None
        else [ExecutionTuple(DEVICE_ID, EXECUTION_ID, COMMAND_UUID)]
    )
    return mock_db


# ---------------------------------------------------------------------------
# assignAction — happy path
# ---------------------------------------------------------------------------


def test_assign_action_happy_path() -> None:
    """assignAction happy path returns AssignActionResponse dict."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db()

    def db_factory(*_args: Any, **_kwargs: Any) -> MagicMock:
        # auth.py opens Database twice (get_schema_name + has_permission),
        # handler opens it once for repo; use a side_effect cycle
        return auth_db

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", return_value="msg-id-1"),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["executionId"] == EXECUTION_ID
    assert result["commandUuid"] == COMMAND_UUID
    assert result["status"] == "ACTION_PENDING"


def test_assign_action_with_template_happy_path() -> None:
    """assignAction with messageTemplateId passes messageContent to SQS envelope."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        template_row={"id": TEMPLATE_ID, "content": "Lock your device", "is_active": True}
    )

    captured_envelopes: list[dict[str, Any]] = []

    def capture_enqueue(body: dict[str, Any], **_kw: Any) -> str:
        captured_envelopes.append(body)
        return "msg-id"

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", side_effect=capture_enqueue),
    ):
        result = lambda_handler(
            _make_event(
                "assignAction",
                {"deviceId": DEVICE_ID, "actionId": ACTION_ID, "messageTemplateId": TEMPLATE_ID},
            ),
            _make_ctx_mock(),
        )

    assert "errorType" not in result
    assert len(captured_envelopes) == 1
    assert captured_envelopes[0]["messageContent"] == "Lock your device"


# ---------------------------------------------------------------------------
# assignAction — error cases
# ---------------------------------------------------------------------------


def test_assign_action_missing_action_returns_error() -> None:
    """assignAction with unknown actionId → ACTION_NOT_FOUND error."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(action_row=None)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "ACTION_NOT_FOUND"


def test_assign_action_template_not_found_returns_error() -> None:
    """assignAction with unknown templateId → TEMPLATE_NOT_FOUND."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(template_row=None)
    # Override load_message_template to simulate missing template
    repo_db.load_message_template.return_value = None

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event(
                "assignAction",
                {
                    "deviceId": DEVICE_ID,
                    "actionId": ACTION_ID,
                    "messageTemplateId": TEMPLATE_ID,
                },
            ),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "TEMPLATE_NOT_FOUND"


def test_assign_action_template_archived_returns_error() -> None:
    """assignAction with archived template → TEMPLATE_ARCHIVED."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(template_row={"id": TEMPLATE_ID, "content": "old", "is_active": False})

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event(
                "assignAction",
                {
                    "deviceId": DEVICE_ID,
                    "actionId": ACTION_ID,
                    "messageTemplateId": TEMPLATE_ID,
                },
            ),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "TEMPLATE_ARCHIVED"


def test_assign_action_fsm_mismatch_returns_invalid_transition() -> None:
    """assignAction where device state ≠ action.from_state → INVALID_TRANSITION."""
    from db import InvalidDevice

    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        valid_devices=[],
        invalid_devices=[
            InvalidDevice(
                DEVICE_ID,
                "INVALID_TRANSITION: device state 1 does not match action from_state 4",
            )
        ],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "INVALID_TRANSITION"


def test_assign_action_device_not_found_returns_not_found() -> None:
    """assignAction where device UUID not in tenant → NOT_FOUND."""
    from db import InvalidDevice

    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        valid_devices=[],
        invalid_devices=[
            InvalidDevice(DEVICE_ID, f"DEVICE_NOT_FOUND: device {DEVICE_ID} not found")
        ],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "NOT_FOUND"


def test_assign_action_device_busy_returns_device_busy() -> None:
    """assignAction where device lost race → DEVICE_BUSY."""
    from db import ValidDevice

    auth_db = _make_auth_db()
    # Device passes FSM but is absent from execution results (lost race).
    repo_db = _make_repo_db(
        valid_devices=[ValidDevice(DEVICE_ID, 4)],
        invalid_devices=[],
        executions=[],  # race loser: locked none
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "DEVICE_BUSY"


def test_assign_action_sqs_failure_after_commit_still_succeeds() -> None:
    """SQS failure post-commit does NOT fail the user request."""
    from sqs import SqsError

    auth_db = _make_auth_db()
    repo_db = _make_repo_db()

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", side_effect=SqsError("queue unavailable")),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    # Request succeeds even though SQS failed.
    assert "errorType" not in result
    assert result["executionId"] == EXECUTION_ID


def test_assign_action_permission_denied() -> None:
    """Missing permission → FORBIDDEN error dict."""
    auth_db = _make_auth_db(has_perm=False)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
    ):
        result = lambda_handler(
            _make_event("assignAction", {"deviceId": DEVICE_ID, "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# assignBulkAction — happy + partial-failure
# ---------------------------------------------------------------------------


def test_assign_bulk_action_all_valid() -> None:
    """assignBulkAction with all devices valid returns populated valid[] and empty failed[]."""
    dev2 = str(uuid.uuid4())
    exec2 = str(uuid.uuid4())
    cmd2 = str(uuid.uuid4())
    from db import ExecutionTuple, ValidDevice

    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        valid_devices=[ValidDevice(DEVICE_ID, 4), ValidDevice(dev2, 4)],
        invalid_devices=[],
        executions=[
            ExecutionTuple(DEVICE_ID, EXECUTION_ID, COMMAND_UUID),
            ExecutionTuple(dev2, exec2, cmd2),
        ],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", return_value="msg-id"),
    ):
        result = lambda_handler(
            _make_event(
                "assignBulkAction",
                {"deviceIds": [DEVICE_ID, dev2], "actionId": ACTION_ID},
            ),
            _make_ctx_mock(),
        )

    assert len(result["valid"]) == 2
    assert result["failed"] == []
    assert result["valid"][0]["status"] == "ACTION_PENDING"


def test_assign_bulk_action_partial_failure() -> None:
    """assignBulkAction with one FSM-invalid device → 1 valid + 1 failed."""
    from db import ExecutionTuple, InvalidDevice, ValidDevice

    bad_device = str(uuid.uuid4())
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        valid_devices=[ValidDevice(DEVICE_ID, 4)],
        invalid_devices=[
            InvalidDevice(
                bad_device, "INVALID_TRANSITION: device state 1 does not match action from_state 4"
            )
        ],
        executions=[ExecutionTuple(DEVICE_ID, EXECUTION_ID, COMMAND_UUID)],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", return_value="msg-id"),
    ):
        result = lambda_handler(
            _make_event(
                "assignBulkAction",
                {"deviceIds": [DEVICE_ID, bad_device], "actionId": ACTION_ID},
            ),
            _make_ctx_mock(),
        )

    assert len(result["valid"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["deviceId"] == bad_device
    assert "INVALID_TRANSITION" in result["failed"][0]["reason"]


def test_assign_bulk_action_race_loser_in_failed() -> None:
    """Device that passes FSM but loses the UPDATE race ends up in failed[]."""
    from db import ExecutionTuple, ValidDevice

    dev2 = str(uuid.uuid4())
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(
        valid_devices=[ValidDevice(DEVICE_ID, 4), ValidDevice(dev2, 4)],
        invalid_devices=[],
        # Only DEVICE_ID was locked; dev2 lost the race.
        executions=[ExecutionTuple(DEVICE_ID, EXECUTION_ID, COMMAND_UUID)],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.enqueue_action_trigger", return_value="msg-id"),
    ):
        result = lambda_handler(
            _make_event(
                "assignBulkAction",
                {"deviceIds": [DEVICE_ID, dev2], "actionId": ACTION_ID},
            ),
            _make_ctx_mock(),
        )

    assert len(result["valid"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["deviceId"] == dev2
    assert "DEVICE_BUSY" in result["failed"][0]["reason"]


def test_assign_bulk_action_missing_action_returns_error() -> None:
    """assignBulkAction with unknown actionId → ACTION_NOT_FOUND (whole-request)."""
    auth_db = _make_auth_db()
    repo_db = _make_repo_db(action_row=None)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_event(
                "assignBulkAction",
                {"deviceIds": [DEVICE_ID], "actionId": ACTION_ID},
            ),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "ACTION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Dispatch / misc
# ---------------------------------------------------------------------------


def test_unknown_field_returns_appsync_error() -> None:
    """Unknown field → UNKNOWN_FIELD error dict."""
    result = lambda_handler(
        {"info": {"fieldName": "noSuchField"}, "arguments": {}},
        _make_ctx_mock(),
    )
    assert result["errorType"] == "UNKNOWN_FIELD"


def test_missing_field_name_returns_error() -> None:
    """No info.fieldName → UNKNOWN_FIELD."""
    result = lambda_handler({}, _make_ctx_mock())
    assert result["errorType"] == "UNKNOWN_FIELD"


def test_invalid_input_returns_invalid_input_error() -> None:
    """Empty deviceIds → INVALID_INPUT from Pydantic validator."""
    auth_db = _make_auth_db()

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
    ):
        result = lambda_handler(
            _make_event("assignBulkAction", {"deviceIds": [], "actionId": ACTION_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Helpers for P1b tests
# ---------------------------------------------------------------------------

from datetime import UTC, datetime  # noqa: E402


def _make_direct_event(
    field: str,
    args: dict[str, Any],
    cognito_sub: str = "sub-test",
    tenant_id: str = "1",
) -> dict[str, Any]:
    """Event where arguments are direct (no 'input' wrapper) — for query fields."""
    return {
        "info": {"fieldName": field},
        "arguments": args,
        "identity": {"claims": {"sub": cognito_sub, "custom:tenant_id": tenant_id}},
    }


def _make_actionlog_row(batch_id: str = BATCH_ID) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "batch_id": batch_id,
        "action_id": ACTION_ID,
        "created_by": "sub-test",
        "total_devices": 3,
        "status": "IN_PROGRESS",
        "created_at": datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC),
        "error_count": 1,
    }


def _make_actionlog_read_db(
    actionlog_row: dict[str, Any] | None = None,
    list_rows: list[dict[str, Any]] | None = None,
    next_cursor: str | None = None,
    failed_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """DB mock for ActionLog read methods."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_action_log_by_batch_id.return_value = actionlog_row
    mock_db.list_action_logs.return_value = (list_rows or [], next_cursor)
    mock_db.get_failed_devices_for_batch.return_value = failed_rows or []
    return mock_db


def _make_actionlog_auth_db(has_perm: bool = True) -> MagicMock:
    """Auth-phase DB mock configured for actionlog:read permission."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_schema_name.return_value = "dev1"
    mock_db.has_permission.return_value = has_perm
    return mock_db


# ---------------------------------------------------------------------------
# getActionLog
# ---------------------------------------------------------------------------


def test_get_action_log_returns_row() -> None:
    """getActionLog happy path returns ActionLog dict."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(actionlog_row=_make_actionlog_row())

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_direct_event("getActionLog", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result is not None
    assert result["batchId"] == BATCH_ID
    assert result["errorCount"] == 1
    assert result["status"] == "IN_PROGRESS"
    assert "created_by" in result
    assert "created_at" in result


def test_get_action_log_returns_none_when_not_found() -> None:
    """getActionLog returns None (not error) when batch doesn't exist."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(actionlog_row=None)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_direct_event("getActionLog", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result is None


def test_get_action_log_permission_denied() -> None:
    """getActionLog without actionlog:read → FORBIDDEN."""
    auth_db = _make_actionlog_auth_db(has_perm=False)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
    ):
        result = lambda_handler(
            _make_direct_event("getActionLog", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# listActionLogs
# ---------------------------------------------------------------------------


def test_list_action_logs_returns_items_and_null_cursor() -> None:
    """listActionLogs happy path returns items list and null nextToken."""
    rows = [_make_actionlog_row(), _make_actionlog_row()]
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(list_rows=rows, next_cursor=None)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_direct_event("listActionLogs", {"limit": 20}),
            _make_ctx_mock(),
        )

    assert len(result["items"]) == 2
    assert result["nextToken"] is None


def test_list_action_logs_returns_next_token_when_more_pages() -> None:
    """listActionLogs returns nextToken when db indicates more pages."""
    rows = [_make_actionlog_row()]
    cursor = "some-cursor-token"
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(list_rows=rows, next_cursor=cursor)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_direct_event("listActionLogs", {"limit": 1}),
            _make_ctx_mock(),
        )

    assert result["nextToken"] == cursor


def test_list_action_logs_default_limit_used() -> None:
    """listActionLogs passes limit=20 by default when not specified."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(list_rows=[])

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        lambda_handler(
            _make_direct_event("listActionLogs", {}),
            _make_ctx_mock(),
        )

    repo_db.list_action_logs.assert_called_once_with(limit=20, after_cursor=None, schema="dev1")


# ---------------------------------------------------------------------------
# generateActionLogErrorReport
# ---------------------------------------------------------------------------


def test_generate_error_report_happy_path() -> None:
    """generateActionLogErrorReport returns batchId, url, expiresAt."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(
        actionlog_row=_make_actionlog_row(),
        failed_rows=[
            {
                "device_id": DEVICE_ID,
                "error_code": "TIMEOUT",
                "error_message": "timed out",
                "finished_at": "2026-04-26T10:00:00+00:00",
            }
        ],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.put_csv"),
        patch("handler.presigned_get_url", return_value="https://s3.example.com/signed-url"),
    ):
        result = lambda_handler(
            _make_direct_event("generateActionLogErrorReport", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result["batchId"] == BATCH_ID
    assert result["url"] == "https://s3.example.com/signed-url"
    assert "expiresAt" in result
    # expiresAt must be ISO-8601 string with timezone offset
    assert "+" in result["expiresAt"] or result["expiresAt"].endswith("Z")


def test_generate_error_report_empty_failed_rows_still_returns_url() -> None:
    """0 failed rows produces header-only CSV and returns URL (no error raised)."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(
        actionlog_row=_make_actionlog_row(),
        failed_rows=[],
    )

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.put_csv"),
        patch("handler.presigned_get_url", return_value="https://s3.example.com/empty-url"),
    ):
        result = lambda_handler(
            _make_direct_event("generateActionLogErrorReport", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert "errorType" not in result
    assert result["url"] == "https://s3.example.com/empty-url"


def test_generate_error_report_batch_not_found_returns_error() -> None:
    """generateActionLogErrorReport with unknown batchId → BATCH_NOT_FOUND."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(actionlog_row=None)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
    ):
        result = lambda_handler(
            _make_direct_event("generateActionLogErrorReport", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "BATCH_NOT_FOUND"


def test_generate_error_report_s3_error_propagates() -> None:
    """S3Error from put_csv propagates as S3_ERROR."""
    from exceptions import S3Error

    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(actionlog_row=_make_actionlog_row(), failed_rows=[])

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.put_csv", side_effect=S3Error("bucket unavailable")),
    ):
        result = lambda_handler(
            _make_direct_event("generateActionLogErrorReport", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert result["errorType"] == "S3_ERROR"


def test_generate_error_report_s3_key_contains_batch_id() -> None:
    """S3 key passed to put_csv contains the batchId."""
    auth_db = _make_actionlog_auth_db()
    repo_db = _make_actionlog_read_db(actionlog_row=_make_actionlog_row(), failed_rows=[])
    captured_keys: list[str] = []

    def capture_put(key: str, body: bytes, **_kw: Any) -> None:
        captured_keys.append(key)

    with (
        patch("auth.Database", return_value=auth_db),
        patch("auth._resolve_user_id", return_value=1),
        patch("handler.Database", return_value=repo_db),
        patch("handler.put_csv", side_effect=capture_put),
        patch("handler.presigned_get_url", return_value="https://s3.example.com/url"),
    ):
        lambda_handler(
            _make_direct_event("generateActionLogErrorReport", {"batchId": BATCH_ID}),
            _make_ctx_mock(),
        )

    assert len(captured_keys) == 1
    assert BATCH_ID in captured_keys[0]
