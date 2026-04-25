"""Unit tests for user_resolver db.py — covers all 7 DB methods."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import psycopg
import pytest

NOW = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)

USER_ROW = {
    "id": 1,
    "email": "alice@example.com",
    "cognito_sub": "sub-alice",
    "name": "Alice",
    "enabled": True,
    "created_at": NOW,
}


def _mock_conn(fetchone_val: Any = None, fetchall_val: list[Any] | None = None) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_val
    cur.fetchall.return_value = fetchall_val or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    return conn


class TestGetUserById:
    def test_happy_path(self) -> None:
        from db import Database

        conn = _mock_conn(fetchone_val=USER_ROW)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                row = db.get_user_by_id(1)
        assert row["email"] == "alice@example.com"

    def test_not_found_raises(self) -> None:
        from db import Database
        from exceptions import NotFoundError

        conn = _mock_conn(fetchone_val=None)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(NotFoundError):
                    db.get_user_by_id(999)


class TestGetUserByCognitoSub:
    def test_happy_path(self) -> None:
        from db import Database

        conn = _mock_conn(fetchone_val=USER_ROW)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                row = db.get_user_by_cognito_sub("sub-alice")
        assert row["id"] == 1

    def test_not_found_raises(self) -> None:
        from db import Database
        from exceptions import NotFoundError

        conn = _mock_conn(fetchone_val=None)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(NotFoundError):
                    db.get_user_by_cognito_sub("no-such-sub")


class TestListUsers:
    def test_returns_rows(self) -> None:
        from db import Database

        conn = _mock_conn(fetchall_val=[USER_ROW])
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                rows = db.list_users(limit=10)
        assert len(rows) == 1

    def test_with_after_id_uses_cursor(self) -> None:
        from db import Database

        conn = _mock_conn(fetchall_val=[USER_ROW])
        with patch("psycopg.connect", return_value=conn) as mock_connect:
            with Database() as db:
                rows = db.list_users(limit=10, after_id=5)
        assert len(rows) == 1
        # Verify WHERE id > %s was used (params contain after_id before limit)
        execute_call = mock_connect.return_value.cursor.return_value.execute
        call_args = execute_call.call_args
        assert 5 in call_args[0][1]


class TestCreateUserPlaceholder:
    def test_happy_path_returns_id(self) -> None:
        from db import Database

        conn = _mock_conn(fetchone_val={"id": 42})
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                user_id = db.create_user_placeholder("new@example.com", "New User")
        assert user_id == 42
        conn.commit.assert_called_once()

    def test_duplicate_email_raises_invalid_input(self) -> None:
        from db import Database
        from exceptions import InvalidInputError

        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.execute.side_effect = psycopg.errors.UniqueViolation("duplicate key")
        conn = MagicMock()
        conn.cursor.return_value = cur
        conn.commit = MagicMock()
        conn.rollback = MagicMock()

        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(InvalidInputError):
                    db.create_user_placeholder("dup@example.com", "Dup")


class TestSetUserCognitoSub:
    def test_happy_path(self) -> None:
        from db import Database

        conn = _mock_conn(fetchone_val={"id": 1})
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                db.set_user_cognito_sub(1, "new-sub")
        conn.commit.assert_called_once()

    def test_row_vanished_raises_not_found(self) -> None:
        from db import Database
        from exceptions import NotFoundError

        conn = _mock_conn(fetchone_val=None)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(NotFoundError):
                    db.set_user_cognito_sub(999, "sub-xyz")


class TestDeleteUser:
    def test_happy_path_commits(self) -> None:
        from db import Database

        conn = _mock_conn()
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                db.delete_user(1)
        conn.commit.assert_called_once()


class TestUpdateUser:
    def test_patch_name(self) -> None:
        from db import Database

        updated = {**USER_ROW, "name": "Updated"}
        conn = _mock_conn(fetchone_val=updated)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                row = db.update_user(1, {"name": "Updated"})
        assert row["name"] == "Updated"

    def test_no_db_fields_raises(self) -> None:
        """role-only patch (Cognito-side) must raise InvalidInputError."""
        from db import Database
        from exceptions import InvalidInputError

        conn = _mock_conn()
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(InvalidInputError):
                    db.update_user(1, {"role": "ADMIN"})

    def test_not_found_raises(self) -> None:
        from db import Database
        from exceptions import NotFoundError

        conn = _mock_conn(fetchone_val=None)
        with patch("psycopg.connect", return_value=conn):
            with Database() as db:
                with pytest.raises(NotFoundError):
                    db.update_user(999, {"name": "Ghost"})


class TestCursorEncoding:
    def test_round_trip(self) -> None:
        from db import _decode_cursor, _encode_cursor

        assert _decode_cursor(_encode_cursor(42)) == 42
        assert _decode_cursor(_encode_cursor(9999999)) == 9999999

    def test_invalid_cursor_raises(self) -> None:
        from db import _decode_cursor
        from exceptions import InvalidInputError

        with pytest.raises(InvalidInputError):
            _decode_cursor("not-base64!!")
