"""Unit tests for db.py — mocks psycopg3 connection, validates query logic and error paths."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from db import Database, _validate_schema
from exceptions import DatabaseError, NotFoundError, TenantNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTION_ID = str(uuid.uuid4())
SCHEMA = "dev1"


def _make_db(schema: str = SCHEMA) -> Database:
    return Database()


_UNSET = object()  # sentinel to distinguish "not provided" from explicit None


def _mock_conn(
    rows: list[dict[str, Any]] | None = None,
    one_row: dict[str, Any] | None | object = _UNSET,
) -> MagicMock:
    """Return a mock psycopg connection with cursor producing given rows.

    Pass ``one_row=None`` to make fetchone() return None (simulates "not found").
    Omit ``one_row`` to leave fetchone() as a live MagicMock (not needed for that test).
    """
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    if rows is not None:
        cur.fetchall.return_value = rows
    if one_row is not _UNSET:
        cur.fetchone.return_value = one_row
    return conn


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------


def test_validate_schema_valid() -> None:
    assert _validate_schema("dev1") == "dev1"


def test_validate_schema_invalid_raises() -> None:
    with pytest.raises(DatabaseError):
        _validate_schema("BAD SCHEMA!")


# ---------------------------------------------------------------------------
# _require_conn — used outside context manager
# ---------------------------------------------------------------------------


def test_require_conn_outside_ctx_raises() -> None:
    db = _make_db()
    with pytest.raises(DatabaseError, match="outside context manager"):
        db._require_conn()  # noqa: SLF001


# ---------------------------------------------------------------------------
# get_schema_name
# ---------------------------------------------------------------------------


def test_get_schema_name_found() -> None:
    db = _make_db()
    conn = _mock_conn(one_row={"schema_name": "dev1"})
    db._conn = conn  # noqa: SLF001
    result = db.get_schema_name(1)
    assert result == "dev1"


def test_get_schema_name_not_found_raises() -> None:
    db = _make_db()
    conn = _mock_conn(one_row=None)
    db._conn = conn  # noqa: SLF001
    with pytest.raises(TenantNotFoundError):
        db.get_schema_name(999)


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------


def test_has_permission_true() -> None:
    db = _make_db()
    conn = _mock_conn(one_row={"1": 1})
    db._conn = conn  # noqa: SLF001
    assert db.has_permission("sub", 1, "platform:read") is True


def test_has_permission_false() -> None:
    db = _make_db()
    conn = _mock_conn(one_row=None)
    db._conn = conn  # noqa: SLF001
    assert db.has_permission("sub", 1, "platform:admin") is False


# ---------------------------------------------------------------------------
# list_states
# ---------------------------------------------------------------------------


def test_list_states_no_filter() -> None:
    db = _make_db()
    rows = [{"id": 1, "name": "Idle"}, {"id": 2, "name": "Registered"}]
    conn = _mock_conn(rows=rows)
    db._conn = conn  # noqa: SLF001
    result = db.list_states(schema=SCHEMA)
    assert len(result) == 2
    assert result[0]["name"] == "Idle"


def test_list_states_with_service_type_filter() -> None:
    db = _make_db()
    rows = [{"id": 4, "name": "Active"}]
    conn = _mock_conn(rows=rows)
    db._conn = conn  # noqa: SLF001
    result = db.list_states(service_type_id=3, schema=SCHEMA)
    assert len(result) == 1


def test_list_states_db_error_raises() -> None:
    import psycopg

    db = _make_db()
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.execute.side_effect = psycopg.OperationalError("connection lost")
    db._conn = conn  # noqa: SLF001
    with pytest.raises(DatabaseError):
        db.list_states(schema=SCHEMA)


# ---------------------------------------------------------------------------
# list_policies
# ---------------------------------------------------------------------------


def test_list_policies_no_filter() -> None:
    db = _make_db()
    rows = [{"id": 4, "name": "Active", "state_id": 4, "service_type_id": 3, "color": None}]
    conn = _mock_conn(rows=rows)
    db._conn = conn  # noqa: SLF001
    result = db.list_policies(schema=SCHEMA)
    assert len(result) == 1
    assert result[0]["name"] == "Active"


def test_list_policies_with_filter() -> None:
    db = _make_db()
    conn = _mock_conn(rows=[])
    db._conn = conn  # noqa: SLF001
    result = db.list_policies(service_type_id=1, schema=SCHEMA)
    assert result == []


# ---------------------------------------------------------------------------
# list_actions
# ---------------------------------------------------------------------------


def test_list_actions_no_filter() -> None:
    db = _make_db()
    row = {
        "id": ACTION_ID,
        "name": "Lock",
        "action_type_id": 5,
        "from_state_id": 4,
        "service_type_id": 3,
        "apply_policy_id": 5,
        "configuration": None,
    }
    conn = _mock_conn(rows=[row])
    db._conn = conn  # noqa: SLF001
    result = db.list_actions(schema=SCHEMA)
    assert len(result) == 1
    assert str(result[0]["id"]) == ACTION_ID


def test_list_actions_with_both_filters() -> None:
    db = _make_db()
    conn = _mock_conn(rows=[])
    db._conn = conn  # noqa: SLF001
    result = db.list_actions(from_state_id=4, service_type_id=3, schema=SCHEMA)
    assert result == []


# ---------------------------------------------------------------------------
# list_services
# ---------------------------------------------------------------------------


def test_list_services_returns_all() -> None:
    db = _make_db()
    rows = [
        {"id": 1, "name": "Inventory", "is_enabled": True},
        {"id": 2, "name": "Supply Chain", "is_enabled": False},
    ]
    conn = _mock_conn(rows=rows)
    db._conn = conn  # noqa: SLF001
    result = db.list_services(schema=SCHEMA)
    assert len(result) == 2
    assert result[1]["is_enabled"] is False


# ---------------------------------------------------------------------------
# update_state
# ---------------------------------------------------------------------------


def test_update_state_success() -> None:
    db = _make_db()
    updated = {"id": 1, "name": "Idle-v2"}
    conn = _mock_conn(one_row=updated)
    db._conn = conn  # noqa: SLF001
    result = db.update_state(1, {"name": "Idle-v2"}, schema=SCHEMA)
    assert result["name"] == "Idle-v2"


def test_update_state_not_found_raises() -> None:
    db = _make_db()
    conn = _mock_conn(one_row=None)
    db._conn = conn  # noqa: SLF001
    with pytest.raises(NotFoundError):
        db.update_state(999, {"name": "Ghost"}, schema=SCHEMA)


# ---------------------------------------------------------------------------
# update_policy
# ---------------------------------------------------------------------------


def test_update_policy_partial_fields() -> None:
    db = _make_db()
    updated = {"id": 4, "name": "Active-v2", "state_id": 4, "service_type_id": 3, "color": "ff0000"}
    conn = _mock_conn(one_row=updated)
    db._conn = conn  # noqa: SLF001
    result = db.update_policy(4, {"name": "Active-v2", "color": "ff0000"}, schema=SCHEMA)
    assert result["color"] == "ff0000"


# ---------------------------------------------------------------------------
# update_action — configuration JSON parsing
# ---------------------------------------------------------------------------


def test_update_action_with_json_string_configuration() -> None:
    db = _make_db()
    updated = {
        "id": ACTION_ID,
        "name": "Lock",
        "action_type_id": 5,
        "from_state_id": 4,
        "service_type_id": 3,
        "apply_policy_id": 5,
        "configuration": {"timeout": 30},
    }
    conn = _mock_conn(one_row=updated)
    db._conn = conn  # noqa: SLF001
    # Pass configuration as JSON string (as AppSync sends AWSJSON as string)
    result = db.update_action(ACTION_ID, {"configuration": '{"timeout": 30}'}, schema=SCHEMA)
    assert result["id"] == ACTION_ID


def test_update_action_invalid_json_configuration_raises() -> None:
    db = _make_db()
    conn = MagicMock()
    db._conn = conn  # noqa: SLF001
    from exceptions import InvalidInputError

    with pytest.raises(InvalidInputError, match="not valid JSON"):
        db.update_action(ACTION_ID, {"configuration": "not-json{"}, schema=SCHEMA)


# ---------------------------------------------------------------------------
# update_service
# ---------------------------------------------------------------------------


def test_update_service_success() -> None:
    db = _make_db()
    updated = {"id": 2, "name": "Supply Chain", "is_enabled": True}
    conn = _mock_conn(one_row=updated)
    db._conn = conn  # noqa: SLF001
    result = db.update_service(2, {"isEnabled": True}, schema=SCHEMA)
    assert result["is_enabled"] is True


def test_update_service_not_found_raises() -> None:
    db = _make_db()
    conn = _mock_conn(one_row=None)
    db._conn = conn  # noqa: SLF001
    with pytest.raises(NotFoundError):
        db.update_service(999, {"name": "Ghost"}, schema=SCHEMA)


# ---------------------------------------------------------------------------
# context manager — close on exit
# ---------------------------------------------------------------------------


def test_database_context_manager_closes_conn() -> None:
    with patch("psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        db = Database()
        with db:
            pass
        mock_conn.close.assert_called_once()


def test_database_context_manager_connect_failure_raises() -> None:
    import psycopg

    with patch("psycopg.connect", side_effect=psycopg.OperationalError("refused")):
        db = Database()
        with pytest.raises(DatabaseError, match="connection failed"):
            db.__enter__()
