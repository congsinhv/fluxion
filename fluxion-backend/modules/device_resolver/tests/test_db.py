"""Unit tests for db.py — uses psycopg fake connection, no real DB."""

from __future__ import annotations

import base64
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from db import Database, _decode_cursor, _encode_cursor, _validate_schema
from exceptions import DatabaseError, InvalidInputError, NotFoundError, TenantNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA = "dev1"
DEVICE_ID = str(uuid.uuid4())
DI_ID = str(uuid.uuid4())

_DEVICE_ROW: dict[str, Any] = {
    "id": DEVICE_ID,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "di_id": DI_ID,
    "serial_number": "SN123",
    "udid": "UDID123",
    "di_name": "iPhone 14",
    "model": "A2650",
    "os_version": "17.0",
    "battery_level": 0.9,
    "wifi_mac": "AA:BB:CC:DD:EE:FF",
    "is_supervised": True,
    "last_checkin_at": "2026-01-01T00:00:00+00:00",
    "ext_fields": None,
}

_MILESTONE_ROW: dict[str, Any] = {
    "id": str(uuid.uuid4()),
    "device_id": DEVICE_ID,
    "assigned_action_id": None,
    "policy_id": 4,
    "created_at": "2026-01-01T00:00:00+00:00",
    "ext_fields": None,
}


def _make_db(rows: list[dict[str, Any]]) -> tuple[Database, MagicMock]:
    """Return a Database instance with a fake psycopg connection returning `rows`."""
    db = Database(dsn="fake://", tenant_schema=SCHEMA)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = rows[0] if rows else None
    mock_cur.fetchall.return_value = rows
    mock_conn.cursor.return_value = mock_cur
    db._conn = mock_conn  # noqa: SLF001
    return db, mock_cur


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------


def test_validate_schema_valid() -> None:
    assert _validate_schema("dev1") == "dev1"


def test_validate_schema_invalid() -> None:
    with pytest.raises(DatabaseError):
        _validate_schema("BAD SCHEMA!")


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def test_encode_decode_cursor_roundtrip() -> None:
    uid = str(uuid.uuid4())
    assert _decode_cursor(_encode_cursor(uid)) == uid


def test_decode_cursor_invalid_base64() -> None:
    with pytest.raises(InvalidInputError):
        _decode_cursor("not-valid!!!")


def test_decode_cursor_invalid_uuid() -> None:
    not_uuid = base64.urlsafe_b64encode(b"notauuid").decode()
    with pytest.raises(InvalidInputError):
        _decode_cursor(not_uuid)


# ---------------------------------------------------------------------------
# Database context manager
# ---------------------------------------------------------------------------


def test_database_requires_conn_outside_cm() -> None:
    db = Database(dsn="fake://", tenant_schema=SCHEMA)
    with pytest.raises(DatabaseError, match="outside context manager"):
        db._require_conn()  # noqa: SLF001


def test_database_connect_failure() -> None:
    import psycopg

    db = Database(dsn="fake://", tenant_schema=SCHEMA)
    with patch("psycopg.connect", side_effect=psycopg.OperationalError("fail")):
        with pytest.raises(DatabaseError, match="connection failed"):
            db.__enter__()


# ---------------------------------------------------------------------------
# get_schema_name
# ---------------------------------------------------------------------------


def test_get_schema_name_found() -> None:
    db, _ = _make_db([{"schema_name": "dev1"}])
    assert db.get_schema_name(1) == "dev1"


def test_get_schema_name_not_found() -> None:
    db, mock_cur = _make_db([])
    mock_cur.fetchone.return_value = None
    with pytest.raises(TenantNotFoundError):
        db.get_schema_name(999)


def test_get_schema_name_db_error() -> None:
    import psycopg

    db, mock_cur = _make_db([])
    mock_cur.execute.side_effect = psycopg.OperationalError("down")
    with pytest.raises(DatabaseError):
        db.get_schema_name(1)


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------


def test_has_permission_true() -> None:
    db, mock_cur = _make_db([{"1": 1}])
    mock_cur.fetchone.return_value = {"1": 1}
    assert db.has_permission("sub", 1, "device:read") is True


def test_has_permission_false() -> None:
    db, mock_cur = _make_db([])
    mock_cur.fetchone.return_value = None
    assert db.has_permission("sub", 1, "device:read") is False


def test_has_permission_db_error() -> None:
    import psycopg

    db, mock_cur = _make_db([])
    mock_cur.execute.side_effect = psycopg.OperationalError("down")
    with pytest.raises(DatabaseError):
        db.has_permission("sub", 1, "device:read")


# ---------------------------------------------------------------------------
# get_device_by_id
# ---------------------------------------------------------------------------


def test_get_device_by_id_found() -> None:
    db, mock_cur = _make_db([_DEVICE_ROW])
    mock_cur.fetchone.return_value = _DEVICE_ROW
    result = db.get_device_by_id(DEVICE_ID)
    assert result["id"] == DEVICE_ID


def test_get_device_by_id_not_found() -> None:
    db, mock_cur = _make_db([])
    mock_cur.fetchone.return_value = None
    with pytest.raises(NotFoundError):
        db.get_device_by_id(DEVICE_ID)


def test_get_device_by_id_db_error() -> None:
    import psycopg

    db, mock_cur = _make_db([])
    mock_cur.execute.side_effect = psycopg.OperationalError("down")
    with pytest.raises(DatabaseError):
        db.get_device_by_id(DEVICE_ID)


# ---------------------------------------------------------------------------
# list_devices
# ---------------------------------------------------------------------------


def test_list_devices_no_cursor() -> None:
    db, mock_cur = _make_db([_DEVICE_ROW])
    mock_cur.fetchall.return_value = [_DEVICE_ROW]
    rows, next_token = db.list_devices(limit=20, after_id=None)
    assert len(rows) == 1
    assert next_token is None


def test_list_devices_next_page() -> None:
    # Return limit+1 rows → next_token populated
    uid1, uid2 = str(uuid.uuid4()), str(uuid.uuid4())
    row1 = {**_DEVICE_ROW, "id": uid1}
    row2 = {**_DEVICE_ROW, "id": uid2}
    db, mock_cur = _make_db([row1, row2])
    mock_cur.fetchall.return_value = [row1, row2]
    rows, next_token = db.list_devices(limit=1, after_id=None)
    assert len(rows) == 1
    assert next_token == _encode_cursor(uid1)


def test_list_devices_with_cursor() -> None:
    db, mock_cur = _make_db([_DEVICE_ROW])
    mock_cur.fetchall.return_value = [_DEVICE_ROW]
    cursor = _encode_cursor(str(uuid.uuid4()))
    rows, _ = db.list_devices(limit=20, after_id=cursor)
    assert len(rows) == 1


def test_list_devices_db_error() -> None:
    import psycopg

    db, mock_cur = _make_db([])
    mock_cur.execute.side_effect = psycopg.OperationalError("down")
    with pytest.raises(DatabaseError):
        db.list_devices(limit=20, after_id=None)


# ---------------------------------------------------------------------------
# get_device_history
# ---------------------------------------------------------------------------


def test_get_device_history_no_cursor() -> None:
    db, mock_cur = _make_db([_MILESTONE_ROW])
    mock_cur.fetchall.return_value = [_MILESTONE_ROW]
    rows, next_token = db.get_device_history(DEVICE_ID, limit=20, after_id=None)
    assert len(rows) == 1
    assert next_token is None


def test_get_device_history_next_page() -> None:
    uid1, uid2 = str(uuid.uuid4()), str(uuid.uuid4())
    m1 = {**_MILESTONE_ROW, "id": uid1}
    m2 = {**_MILESTONE_ROW, "id": uid2}
    db, mock_cur = _make_db([m1, m2])
    mock_cur.fetchall.return_value = [m1, m2]
    rows, next_token = db.get_device_history(DEVICE_ID, limit=1, after_id=None)
    assert len(rows) == 1
    assert next_token == _encode_cursor(uid1)


def test_get_device_history_with_cursor() -> None:
    db, mock_cur = _make_db([_MILESTONE_ROW])
    mock_cur.fetchall.return_value = [_MILESTONE_ROW]
    cursor = _encode_cursor(str(uuid.uuid4()))
    rows, _ = db.get_device_history(DEVICE_ID, limit=20, after_id=cursor)
    assert len(rows) == 1


def test_get_device_history_db_error() -> None:
    import psycopg

    db, mock_cur = _make_db([])
    mock_cur.execute.side_effect = psycopg.OperationalError("down")
    with pytest.raises(DatabaseError):
        db.get_device_history(DEVICE_ID, limit=20, after_id=None)
