"""Unit tests for upload_resolver db.py.

All tests use a mock psycopg connection — no real DB required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from db import Database, ExistingDeviceKeys, _validate_schema
from exceptions import DatabaseError, TenantNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db(fetchone_return: Any = None, fetchall_return: Any = None) -> MagicMock:
    """Build a mock Database that returns preset values from cursor methods."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = fetchone_return
    mock_cur.fetchall.return_value = fetchall_return or []
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------


class TestValidateSchema:
    def test_valid_simple(self) -> None:
        assert _validate_schema("dev1") == "dev1"

    def test_valid_with_underscore(self) -> None:
        assert _validate_schema("tenant_abc") == "tenant_abc"

    def test_valid_max_length(self) -> None:
        name = "a" + "b" * 39  # 40 chars
        assert _validate_schema(name) == name

    def test_invalid_uppercase(self) -> None:
        with pytest.raises(DatabaseError):
            _validate_schema("DEV1")

    def test_invalid_starts_with_digit(self) -> None:
        with pytest.raises(DatabaseError):
            _validate_schema("1dev")

    def test_invalid_too_long(self) -> None:
        with pytest.raises(DatabaseError):
            _validate_schema("a" * 41)

    def test_invalid_empty(self) -> None:
        with pytest.raises(DatabaseError):
            _validate_schema("")


# ---------------------------------------------------------------------------
# Database.get_schema_name
# ---------------------------------------------------------------------------


class TestGetSchemaName:
    def test_returns_schema_name(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchone_return={"schema_name": "dev1"})
        result = db.get_schema_name(1)
        assert result == "dev1"

    def test_raises_tenant_not_found(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchone_return=None)
        with pytest.raises(TenantNotFoundError):
            db.get_schema_name(99)

    def test_raises_database_error_on_psycopg(self) -> None:
        import psycopg

        db = Database()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.execute.side_effect = psycopg.OperationalError("conn error")
        mock_conn.cursor.return_value = mock_cur
        db._conn = mock_conn
        with pytest.raises(DatabaseError):
            db.get_schema_name(1)


# ---------------------------------------------------------------------------
# Database.has_permission
# ---------------------------------------------------------------------------


class TestHasPermission:
    def test_returns_true_when_row_found(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchone_return={"1": 1})
        assert db.has_permission("sub-abc", 1, "upload:write") is True

    def test_returns_false_when_no_row(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchone_return=None)
        assert db.has_permission("sub-abc", 1, "upload:write") is False

    def test_raises_database_error_on_psycopg(self) -> None:
        import psycopg

        db = Database()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.execute.side_effect = psycopg.OperationalError("err")
        mock_conn.cursor.return_value = mock_cur
        db._conn = mock_conn
        with pytest.raises(DatabaseError):
            db.has_permission("sub", 1, "upload:write")


# ---------------------------------------------------------------------------
# Database.find_existing_device_keys
# ---------------------------------------------------------------------------


class TestFindExistingDeviceKeys:
    def test_returns_empty_when_no_rows(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[])
        result = db.find_existing_device_keys(["SN001"], ["UDID001"], "dev1")
        assert result == ExistingDeviceKeys(serials=set(), udids=set())

    def test_returns_matching_serial(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[{"serial_number": "SN001", "udid": "UDID-OTHER"}])
        result = db.find_existing_device_keys(["SN001"], ["UDID001"], "dev1")
        assert "SN001" in result.serials
        assert "UDID-OTHER" in result.udids

    def test_returns_matching_udid(self) -> None:
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[{"serial_number": "SN-OTHER", "udid": "UDID001"}])
        result = db.find_existing_device_keys(["SN999"], ["UDID001"], "dev1")
        assert "UDID001" in result.udids

    def test_multiple_conflicts(self) -> None:
        db = Database()
        db._conn = _make_mock_db(
            fetchall_return=[
                {"serial_number": "SN001", "udid": "UDID001"},
                {"serial_number": "SN002", "udid": "UDID002"},
            ]
        )
        result = db.find_existing_device_keys(["SN001", "SN002"], ["UDID001", "UDID002"], "dev1")
        assert result.serials == {"SN001", "SN002"}
        assert result.udids == {"UDID001", "UDID002"}

    def test_empty_inputs_skip_query(self) -> None:
        """Empty serials + udids returns empty sets without touching DB."""
        db = Database()
        mock_conn = MagicMock()
        db._conn = mock_conn
        result = db.find_existing_device_keys([], [], "dev1")
        assert result == ExistingDeviceKeys(serials=set(), udids=set())
        mock_conn.cursor.assert_not_called()

    def test_handles_none_values_in_row(self) -> None:
        """Row with NULL columns should not add None to sets."""
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[{"serial_number": None, "udid": None}])
        result = db.find_existing_device_keys(["SN001"], ["UDID001"], "dev1")
        assert result.serials == set()
        assert result.udids == set()

    def test_invalid_schema_raises(self) -> None:
        db = Database()
        db._conn = MagicMock()
        with pytest.raises(DatabaseError, match="invalid schema_name"):
            db.find_existing_device_keys(["SN001"], ["U1"], "INVALID")

    def test_raises_database_error_on_psycopg(self) -> None:
        import psycopg

        db = Database()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.execute.side_effect = psycopg.OperationalError("err")
        mock_conn.cursor.return_value = mock_cur
        db._conn = mock_conn
        with pytest.raises(DatabaseError):
            db.find_existing_device_keys(["SN001"], ["UDID001"], "dev1")

    def test_empty_serials_uses_sentinel(self) -> None:
        """When serials is empty but udids is not, query is still executed with sentinel."""
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[])
        # Should not raise — sentinel prevents empty array in ANY()
        result = db.find_existing_device_keys([], ["UDID001"], "dev1")
        assert result == ExistingDeviceKeys(serials=set(), udids=set())

    def test_empty_udids_uses_sentinel(self) -> None:
        """When udids is empty but serials is not, query is still executed with sentinel."""
        db = Database()
        db._conn = _make_mock_db(fetchall_return=[])
        result = db.find_existing_device_keys(["SN001"], [], "dev1")
        assert result == ExistingDeviceKeys(serials=set(), udids=set())


# ---------------------------------------------------------------------------
# Database context manager
# ---------------------------------------------------------------------------


class TestDatabaseContextManager:
    def test_require_conn_raises_outside_context(self) -> None:
        db = Database()
        with pytest.raises(DatabaseError, match="outside context manager"):
            db._require_conn()

    def test_connect_failure_raises_database_error(self) -> None:
        import psycopg

        with patch("db.psycopg.connect", side_effect=psycopg.OperationalError("no server")):
            with pytest.raises(DatabaseError, match="database connection failed"):
                with Database():
                    pass
