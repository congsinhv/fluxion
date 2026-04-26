"""Tests for action_resolver db.py — Database wrapper and repo methods.

Uses unittest.mock to simulate psycopg3 connections; no real PostgreSQL needed.
Covers:
  - get_schema_name: happy path, tenant not found, query error
  - has_permission: granted, denied, query error
  - load_action: found, not found, query error
  - load_message_template: found, not found, query error
  - validate_devices_for_action: all valid, FSM mismatch, device not found, mixed
  - create_batch_with_devices: happy path, all-race-loser, empty input, db error
  - _require_conn: used outside context manager raises DatabaseError
  - _validate_schema: bad names rejected
  - get_action_log_by_batch_id: found, not found, query error
  - list_action_logs: first page, with cursor, has_more, empty
  - get_failed_devices_for_batch: with rows, empty, query error
  - cursor helpers: encode/decode round-trip, bad token, missing separator, bad uuid
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from db import (
    Database,
    ValidDevice,
    _decode_action_log_cursor,
    _encode_action_log_cursor,
    _validate_schema,
)
from exceptions import DatabaseError, InvalidInputError, TenantNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA = "dev1"
ACTION_ID = str(uuid.uuid4())
DEVICE_ID = str(uuid.uuid4())
TEMPLATE_ID = str(uuid.uuid4())
BATCH_ID = str(uuid.uuid4())
EXECUTION_ID = str(uuid.uuid4())
COMMAND_UUID_VAL = str(uuid.uuid4())


def _make_conn(
    fetchone_returns: list[Any] | None = None,
    fetchall_returns: list[Any] | None = None,
    execute_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock psycopg3 connection with a cursor sequence."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    if execute_raises is not None:
        cursor.execute.side_effect = execute_raises
    if fetchone_returns is not None:
        cursor.fetchone.side_effect = fetchone_returns
    if fetchall_returns is not None:
        cursor.fetchall.side_effect = fetchall_returns

    conn.cursor.return_value = cursor
    return conn


def _open_db(conn: MagicMock) -> Database:
    """Return a Database with _conn already set (bypasses psycopg.connect)."""
    db = Database.__new__(Database)
    db._conn = conn  # type: ignore[attr-defined]
    return db


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------


def test_validate_schema_valid_names() -> None:
    assert _validate_schema("dev1") == "dev1"
    assert _validate_schema("a") == "a"
    assert _validate_schema("abc_123") == "abc_123"


def test_validate_schema_rejects_invalid() -> None:
    with pytest.raises(DatabaseError):
        _validate_schema("1invalid")
    with pytest.raises(DatabaseError):
        _validate_schema("has space")
    with pytest.raises(DatabaseError):
        _validate_schema("")
    with pytest.raises(DatabaseError):
        _validate_schema("UPPER")


# ---------------------------------------------------------------------------
# get_schema_name
# ---------------------------------------------------------------------------


def test_get_schema_name_returns_validated_name() -> None:
    conn = _make_conn(fetchone_returns=[{"schema_name": "dev1"}])
    db = _open_db(conn)
    result = db.get_schema_name(1)
    assert result == "dev1"


def test_get_schema_name_tenant_not_found() -> None:
    conn = _make_conn(fetchone_returns=[None])
    db = _open_db(conn)
    with pytest.raises(TenantNotFoundError):
        db.get_schema_name(99)


def test_get_schema_name_query_error_raises_database_error() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("conn lost"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="tenant lookup failed"):
        db.get_schema_name(1)


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------


def test_has_permission_returns_true_when_granted() -> None:
    conn = _make_conn(fetchone_returns=[{"1": 1}])
    db = _open_db(conn)
    assert db.has_permission("sub-1", 1, "action:execute") is True


def test_has_permission_returns_false_when_no_row() -> None:
    conn = _make_conn(fetchone_returns=[None])
    db = _open_db(conn)
    assert db.has_permission("sub-1", 1, "action:execute") is False


def test_has_permission_query_error_raises_database_error() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db down"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="permission check failed"):
        db.has_permission("sub-1", 1, "action:execute")


# ---------------------------------------------------------------------------
# load_action
# ---------------------------------------------------------------------------


def test_load_action_returns_row_when_found() -> None:
    row = {"id": ACTION_ID, "from_state_id": 4, "name": "Lock"}
    conn = _make_conn(fetchone_returns=[row])
    db = _open_db(conn)
    result = db.load_action(ACTION_ID, SCHEMA)
    assert result == row


def test_load_action_returns_none_when_missing() -> None:
    conn = _make_conn(fetchone_returns=[None])
    db = _open_db(conn)
    assert db.load_action(ACTION_ID, SCHEMA) is None


def test_load_action_query_error_raises_database_error() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="load_action query failed"):
        db.load_action(ACTION_ID, SCHEMA)


def test_load_action_invalid_schema_raises() -> None:
    conn = _make_conn()
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="invalid schema_name"):
        db.load_action(ACTION_ID, "1bad")


# ---------------------------------------------------------------------------
# load_message_template
# ---------------------------------------------------------------------------


def test_load_message_template_returns_row_when_found() -> None:
    row = {"id": TEMPLATE_ID, "content": "hello", "is_active": True}
    conn = _make_conn(fetchone_returns=[row])
    db = _open_db(conn)
    result = db.load_message_template(TEMPLATE_ID, SCHEMA)
    assert result == row


def test_load_message_template_returns_none_when_missing() -> None:
    conn = _make_conn(fetchone_returns=[None])
    db = _open_db(conn)
    assert db.load_message_template(TEMPLATE_ID, SCHEMA) is None


def test_load_message_template_query_error_raises() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="load_message_template query failed"):
        db.load_message_template(TEMPLATE_ID, SCHEMA)


# ---------------------------------------------------------------------------
# validate_devices_for_action
# ---------------------------------------------------------------------------


def test_validate_devices_all_valid() -> None:
    rows = [{"id": DEVICE_ID, "state_id": 4, "assigned_action_id": None, "from_state_id": 4}]
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    valid, invalid = db.validate_devices_for_action([DEVICE_ID], ACTION_ID, SCHEMA)
    assert len(valid) == 1
    assert valid[0].device_id == DEVICE_ID
    assert invalid == []


def test_validate_devices_fsm_mismatch() -> None:
    rows = [{"id": DEVICE_ID, "state_id": 1, "assigned_action_id": None, "from_state_id": 4}]
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    valid, invalid = db.validate_devices_for_action([DEVICE_ID], ACTION_ID, SCHEMA)
    assert valid == []
    assert len(invalid) == 1
    assert "INVALID_TRANSITION" in invalid[0].reason


def test_validate_devices_not_found() -> None:
    """Device ID not returned by query → DEVICE_NOT_FOUND invalid entry."""
    missing_id = str(uuid.uuid4())
    conn = _make_conn(fetchall_returns=[[]])  # no rows returned
    db = _open_db(conn)
    valid, invalid = db.validate_devices_for_action([missing_id], ACTION_ID, SCHEMA)
    assert valid == []
    assert len(invalid) == 1
    assert "DEVICE_NOT_FOUND" in invalid[0].reason
    assert invalid[0].device_id == missing_id


def test_validate_devices_mixed() -> None:
    """One valid, one FSM-invalid, one not-found."""
    dev2 = str(uuid.uuid4())
    dev3 = str(uuid.uuid4())  # not returned = not found
    rows = [
        {"id": DEVICE_ID, "state_id": 4, "assigned_action_id": None, "from_state_id": 4},
        {"id": dev2, "state_id": 1, "assigned_action_id": None, "from_state_id": 4},
    ]
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    valid, invalid = db.validate_devices_for_action([DEVICE_ID, dev2, dev3], ACTION_ID, SCHEMA)
    assert len(valid) == 1
    assert valid[0].device_id == DEVICE_ID
    assert len(invalid) == 2
    reasons = {inv.device_id: inv.reason for inv in invalid}
    assert "INVALID_TRANSITION" in reasons[dev2]
    assert "DEVICE_NOT_FOUND" in reasons[dev3]


def test_validate_devices_null_from_state_means_any_state_valid() -> None:
    """Actions with from_state_id=NULL (e.g., Upload) accept any device state."""
    rows = [{"id": DEVICE_ID, "state_id": 3, "assigned_action_id": None, "from_state_id": None}]
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    valid, invalid = db.validate_devices_for_action([DEVICE_ID], ACTION_ID, SCHEMA)
    assert len(valid) == 1
    assert invalid == []


def test_validate_devices_query_error_raises() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="validate_devices_for_action query failed"):
        db.validate_devices_for_action([DEVICE_ID], ACTION_ID, SCHEMA)


# ---------------------------------------------------------------------------
# create_batch_with_devices
# ---------------------------------------------------------------------------


def test_create_batch_with_devices_empty_input_returns_empty() -> None:
    conn = _make_conn()
    db = _open_db(conn)
    result = db.create_batch_with_devices(BATCH_ID, ACTION_ID, "sub-1", [], SCHEMA)
    assert result == []


def test_create_batch_with_devices_happy_path() -> None:
    """All devices locked → returns ExecutionTuple list."""
    valid = [ValidDevice(DEVICE_ID, 4)]

    # Simulate transaction context manager
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    # transaction() context manager
    tx_ctx = MagicMock()
    tx_ctx.__enter__ = MagicMock(return_value=None)
    tx_ctx.__exit__ = MagicMock(return_value=False)
    conn.transaction.return_value = tx_ctx

    # cursor() calls return cursors with specific fetchone/fetchall results
    # Call order: UPDATE RETURNING, INSERT batch_actions, INSERT ae RETURNING, INSERT bda
    lock_cursor = MagicMock()
    lock_cursor.__enter__ = MagicMock(return_value=lock_cursor)
    lock_cursor.__exit__ = MagicMock(return_value=False)
    lock_cursor.fetchall.return_value = [{"id": DEVICE_ID}]

    ba_cursor = MagicMock()
    ba_cursor.__enter__ = MagicMock(return_value=ba_cursor)
    ba_cursor.__exit__ = MagicMock(return_value=False)

    ae_cursor = MagicMock()
    ae_cursor.__enter__ = MagicMock(return_value=ae_cursor)
    ae_cursor.__exit__ = MagicMock(return_value=False)
    ae_cursor.fetchone.return_value = {"id": EXECUTION_ID, "command_uuid": COMMAND_UUID_VAL}

    bda_cursor = MagicMock()
    bda_cursor.__enter__ = MagicMock(return_value=bda_cursor)
    bda_cursor.__exit__ = MagicMock(return_value=False)

    conn.cursor.side_effect = [lock_cursor, ba_cursor, ae_cursor, bda_cursor]

    db = _open_db(conn)
    results = db.create_batch_with_devices(BATCH_ID, ACTION_ID, "sub-1", valid, SCHEMA)

    assert len(results) == 1
    assert results[0].device_id == DEVICE_ID
    assert results[0].execution_id == EXECUTION_ID
    assert results[0].command_uuid == COMMAND_UUID_VAL


def test_create_batch_with_devices_all_race_losers_returns_empty() -> None:
    """UPDATE RETURNING no rows → all devices lost race → empty result."""
    valid = [ValidDevice(DEVICE_ID, 4)]

    conn = MagicMock()
    tx_ctx = MagicMock()
    tx_ctx.__enter__ = MagicMock(return_value=None)
    tx_ctx.__exit__ = MagicMock(return_value=False)
    conn.transaction.return_value = tx_ctx

    lock_cursor = MagicMock()
    lock_cursor.__enter__ = MagicMock(return_value=lock_cursor)
    lock_cursor.__exit__ = MagicMock(return_value=False)
    lock_cursor.fetchall.return_value = []  # no rows locked

    conn.cursor.return_value = lock_cursor

    db = _open_db(conn)
    results = db.create_batch_with_devices(BATCH_ID, ACTION_ID, "sub-1", valid, SCHEMA)

    assert results == []


def test_create_batch_with_devices_db_error_raises() -> None:
    """psycopg error inside transaction → DatabaseError raised."""
    import psycopg

    valid = [ValidDevice(DEVICE_ID, 4)]
    conn = MagicMock()
    tx_ctx = MagicMock()
    tx_ctx.__enter__ = MagicMock(side_effect=psycopg.OperationalError("connection reset"))
    tx_ctx.__exit__ = MagicMock(return_value=False)
    conn.transaction.return_value = tx_ctx

    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="create_batch_with_devices transaction failed"):
        db.create_batch_with_devices(BATCH_ID, ACTION_ID, "sub-1", valid, SCHEMA)


# ---------------------------------------------------------------------------
# _require_conn
# ---------------------------------------------------------------------------


def test_require_conn_outside_context_manager_raises() -> None:
    db = Database()
    with pytest.raises(DatabaseError, match="outside context manager"):
        db._require_conn()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Database context manager
# ---------------------------------------------------------------------------


def test_database_connect_failure_raises_database_error() -> None:
    """psycopg.connect failing → DatabaseError on __enter__."""
    import psycopg

    with patch("db.psycopg.connect", side_effect=psycopg.OperationalError("unreachable")):
        with pytest.raises(DatabaseError, match="database connection failed"):
            with Database():
                pass


# ---------------------------------------------------------------------------
# get_action_log_by_batch_id (P1b)
# ---------------------------------------------------------------------------

_BATCH_ID = str(uuid.uuid4())
_ACTION_ID_2 = str(uuid.uuid4())
_CREATED_AT = datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC)


def _make_action_log_row(
    batch_id: str = _BATCH_ID,
    error_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "batch_id": batch_id,
        "action_id": _ACTION_ID_2,
        "created_by": "sub-abc",
        "total_devices": 5,
        "status": "IN_PROGRESS",
        "created_at": _CREATED_AT,
        "error_count": error_count,
    }


def test_get_action_log_by_batch_id_returns_row() -> None:
    row = _make_action_log_row(error_count=2)
    conn = _make_conn(fetchone_returns=[row])
    db = _open_db(conn)
    result = db.get_action_log_by_batch_id(_BATCH_ID, SCHEMA)
    assert result is not None
    assert result["batch_id"] == _BATCH_ID
    assert result["error_count"] == 2


def test_get_action_log_by_batch_id_returns_none_when_missing() -> None:
    conn = _make_conn(fetchone_returns=[None])
    db = _open_db(conn)
    result = db.get_action_log_by_batch_id(_BATCH_ID, SCHEMA)
    assert result is None


def test_get_action_log_by_batch_id_query_error_raises() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="get_action_log_by_batch_id query failed"):
        db.get_action_log_by_batch_id(_BATCH_ID, SCHEMA)


def test_get_action_log_by_batch_id_invalid_schema_raises() -> None:
    conn = _make_conn()
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="invalid schema_name"):
        db.get_action_log_by_batch_id(_BATCH_ID, "1BAD")


# ---------------------------------------------------------------------------
# list_action_logs (P1b)
# ---------------------------------------------------------------------------


def _make_list_rows(n: int) -> list[dict[str, Any]]:
    return [_make_action_log_row(batch_id=str(uuid.uuid4())) for _ in range(n)]


def test_list_action_logs_first_page_no_cursor() -> None:
    rows = _make_list_rows(3)
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    result, next_cursor = db.list_action_logs(limit=20, after_cursor=None, schema=SCHEMA)
    assert len(result) == 3
    assert next_cursor is None


def test_list_action_logs_returns_next_cursor_when_more_pages() -> None:
    # Return limit+1 rows to signal more pages exist.
    rows = _make_list_rows(6)
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    result, next_cursor = db.list_action_logs(limit=5, after_cursor=None, schema=SCHEMA)
    assert len(result) == 5  # only limit rows returned
    assert next_cursor is not None  # cursor set from last kept row


def test_list_action_logs_with_valid_cursor() -> None:
    ts = datetime(2026, 4, 26, 9, 0, 0, tzinfo=UTC)
    cursor = _encode_action_log_cursor(ts, str(uuid.uuid4()))
    rows = _make_list_rows(2)
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    result, next_cursor = db.list_action_logs(limit=20, after_cursor=cursor, schema=SCHEMA)
    assert len(result) == 2
    assert next_cursor is None


def test_list_action_logs_empty_result() -> None:
    conn = _make_conn(fetchall_returns=[[]])
    db = _open_db(conn)
    result, next_cursor = db.list_action_logs(limit=20, after_cursor=None, schema=SCHEMA)
    assert result == []
    assert next_cursor is None


def test_list_action_logs_invalid_cursor_raises() -> None:
    conn = _make_conn(fetchall_returns=[[]])
    db = _open_db(conn)
    with pytest.raises(InvalidInputError):
        db.list_action_logs(limit=10, after_cursor="!!!not-base64!!!", schema=SCHEMA)


def test_list_action_logs_query_error_raises() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="list_action_logs query failed"):
        db.list_action_logs(limit=10, after_cursor=None, schema=SCHEMA)


# ---------------------------------------------------------------------------
# get_failed_devices_for_batch (P1b)
# ---------------------------------------------------------------------------


def test_get_failed_devices_returns_rows() -> None:
    rows = [
        {
            "device_id": DEVICE_ID,
            "error_code": "TIMEOUT",
            "error_message": "timed out",
            "finished_at": _CREATED_AT,
        }
    ]
    conn = _make_conn(fetchall_returns=[rows])
    db = _open_db(conn)
    result = db.get_failed_devices_for_batch(_BATCH_ID, SCHEMA)
    assert len(result) == 1
    assert result[0]["error_code"] == "TIMEOUT"


def test_get_failed_devices_returns_empty_list_when_no_failures() -> None:
    conn = _make_conn(fetchall_returns=[[]])
    db = _open_db(conn)
    result = db.get_failed_devices_for_batch(_BATCH_ID, SCHEMA)
    assert result == []


def test_get_failed_devices_query_error_raises() -> None:
    import psycopg

    conn = _make_conn(execute_raises=psycopg.OperationalError("db error"))
    db = _open_db(conn)
    with pytest.raises(DatabaseError, match="get_failed_devices_for_batch query failed"):
        db.get_failed_devices_for_batch(_BATCH_ID, SCHEMA)


# ---------------------------------------------------------------------------
# Cursor helpers (P1b)
# ---------------------------------------------------------------------------


def test_cursor_encode_decode_round_trip() -> None:
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    id_ = str(uuid.uuid4())
    token = _encode_action_log_cursor(ts, id_)
    decoded_ts, decoded_id = _decode_action_log_cursor(token)
    assert decoded_ts == ts
    assert str(decoded_id) == id_


def test_cursor_decode_invalid_base64_raises() -> None:
    with pytest.raises(InvalidInputError, match="base64 decode failed"):
        _decode_action_log_cursor("@@@not_base64@@@")


def test_cursor_decode_missing_separator_raises() -> None:
    import base64

    bad = base64.urlsafe_b64encode(b"nodividerhere").decode()
    with pytest.raises(InvalidInputError, match="missing separator"):
        _decode_action_log_cursor(bad)


def test_cursor_decode_bad_datetime_raises() -> None:
    import base64

    bad = base64.urlsafe_b64encode(b"not-a-date|" + str(uuid.uuid4()).encode()).decode()
    with pytest.raises(InvalidInputError, match="bad datetime"):
        _decode_action_log_cursor(bad)


def test_cursor_decode_bad_uuid_raises() -> None:
    import base64

    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC).isoformat()
    bad = base64.urlsafe_b64encode(f"{ts}|not-a-uuid".encode()).decode()
    with pytest.raises(InvalidInputError, match="bad UUID"):
        _decode_action_log_cursor(bad)


def test_cursor_naive_datetime_gets_utc_tzinfo() -> None:
    """Naive datetimes decoded from cursor should become UTC-aware."""
    import base64

    ts = datetime(2026, 4, 26, 12, 0, 0)  # no tzinfo
    id_ = str(uuid.uuid4())
    raw = f"{ts.isoformat()}|{id_}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    decoded_ts, _ = _decode_action_log_cursor(token)
    assert decoded_ts.tzinfo is not None
