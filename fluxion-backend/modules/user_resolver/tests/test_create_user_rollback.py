"""Tests for createUser rollback behaviour.

Verifies that when Cognito admin_create_user fails, the DB placeholder row is
deleted and the exception propagates — no orphan rows left behind.

Connection sequence (matches auth.py + handler.py structure):
  conn#0 (build_context_from): fetchone[0]=schema_row, fetchone[1]=user_id_row
  conn#1 (permission check):   fetchone[0]=perm_row
  conn#2 (create_placeholder): fetchone[0]={"id": 7}
  conn#3 (delete rollback):    no fetchone needed (DELETE has no RETURNING)
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

NOW = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)

USER_ROW = {
    "id": 7,
    "email": "new@example.com",
    "cognito_sub": "sub-new",
    "name": "New User",
    "enabled": True,
    "created_at": NOW,
}


def _make_conn(fetchone_seq: list[Any], fetchall_val: list[Any] | None = None) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = fetchone_seq
    cur.fetchall.return_value = fetchall_val or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    return conn


def _make_event(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "info": {"fieldName": "createUser"},
        "arguments": args,
        "identity": {
            "claims": {
                "sub": "sub-admin",
                "custom:tenant_id": "1",
            }
        },
    }


class FakeLambdaContext:
    aws_request_id = "rollback-test-id"


# ---------------------------------------------------------------------------
# Standard auth connections (conn#0 + conn#1) shared by all tests
# ---------------------------------------------------------------------------


def _auth_conns() -> tuple[MagicMock, MagicMock]:
    conn0 = _make_conn(fetchone_seq=[{"schema_name": "dev1"}, {"id": 99}])
    conn1 = _make_conn(fetchone_seq=[{"1": 1}])  # permission granted
    return conn0, conn1


class TestCreateUserRollback:
    def test_cognito_failure_triggers_db_delete(self) -> None:
        """When admin_create_user raises, delete_user is called and error is returned."""
        from exceptions import CognitoError
        from handler import lambda_handler

        conn0, conn1 = _auth_conns()
        conn2 = _make_conn(fetchone_seq=[{"id": 7}])  # create_user_placeholder
        conn3 = _make_conn(fetchone_seq=[])  # delete_user (no RETURNING)
        conns = [conn0, conn1, conn2, conn3]

        event = _make_event(
            {
                "input": {"email": "new@example.com", "name": "New User", "role": "OPERATOR"},
            }
        )

        delete_called: list[int] = []

        def patched_delete_user(self_db: Any, user_id: int) -> None:  # noqa: ANN001
            delete_called.append(user_id)

        with (
            patch("psycopg.connect", side_effect=conns),
            patch("cognito.admin_create_user", side_effect=CognitoError("pool error")),
            patch("db.Database.delete_user", patched_delete_user),
        ):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "COGNITO_ERROR"
        assert 7 in delete_called, "delete_user must be called with placeholder id=7"

    def test_cognito_failure_no_orphan_sub_in_db(self) -> None:
        """After rollback, set_user_cognito_sub is never called."""
        from exceptions import CognitoError
        from handler import lambda_handler

        conn0, conn1 = _auth_conns()
        conn2 = _make_conn(fetchone_seq=[{"id": 7}])
        conn3 = _make_conn(fetchone_seq=[])
        conns = [conn0, conn1, conn2, conn3]

        event = _make_event(
            {
                "input": {"email": "new@example.com", "name": "New User", "role": "OPERATOR"},
            }
        )

        set_sub_called: list[Any] = []

        def patched_set_sub(self_db: Any, user_id: int, sub: str) -> None:  # noqa: ANN001
            set_sub_called.append((user_id, sub))

        with (
            patch("psycopg.connect", side_effect=conns),
            patch("cognito.admin_create_user", side_effect=CognitoError("create failed")),
            patch("db.Database.delete_user"),
            patch("db.Database.set_user_cognito_sub", patched_set_sub),
        ):
            lambda_handler(event, FakeLambdaContext())

        assert set_sub_called == [], "set_user_cognito_sub must NOT be called after rollback"

    def test_happy_path_no_rollback(self) -> None:
        """Successful createUser does NOT call delete_user."""
        from handler import lambda_handler

        conn0, conn1 = _auth_conns()
        conn2 = _make_conn(fetchone_seq=[{"id": 7}])  # create_user_placeholder
        conn3 = _make_conn(
            fetchone_seq=[{"id": 7}, USER_ROW]
        )  # set_user_cognito_sub + get_user_by_id
        conns = [conn0, conn1, conn2, conn3]

        event = _make_event(
            {
                "input": {"email": "new@example.com", "name": "New User", "role": "OPERATOR"},
            }
        )

        delete_called: list[Any] = []

        def patched_delete(self_db: Any, uid: int) -> None:  # noqa: ANN001
            delete_called.append(uid)

        with (
            patch("psycopg.connect", side_effect=conns),
            patch("cognito.admin_create_user", return_value="sub-new"),
            patch("cognito.admin_update_user_attributes"),
            patch("db.Database.delete_user", patched_delete),
        ):
            result = lambda_handler(event, FakeLambdaContext())

        assert "errorType" not in result, f"unexpected error: {result}"
        assert result["email"] == "new@example.com"
        assert delete_called == [], "delete_user must NOT be called on success"

    def test_admin_update_attributes_failure_triggers_rollback(self) -> None:
        """If admin_update_user_attributes fails after create, rollback fires."""
        from exceptions import CognitoError
        from handler import lambda_handler

        conn0, conn1 = _auth_conns()
        conn2 = _make_conn(fetchone_seq=[{"id": 7}])  # create_user_placeholder
        conn3 = _make_conn(fetchone_seq=[])  # delete_user rollback
        conns = [conn0, conn1, conn2, conn3]

        event = _make_event(
            {
                "input": {"email": "new@example.com", "name": "New User", "role": "ADMIN"},
            }
        )

        delete_called: list[int] = []

        def patched_delete(self_db: Any, uid: int) -> None:  # noqa: ANN001
            delete_called.append(uid)

        with (
            patch("psycopg.connect", side_effect=conns),
            patch("cognito.admin_create_user", return_value="sub-new"),
            patch(
                "cognito.admin_update_user_attributes",
                side_effect=CognitoError("attr update failed"),
            ),
            patch("db.Database.delete_user", patched_delete),
        ):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "COGNITO_ERROR"
        assert 7 in delete_called, "delete_user must be called when attr update fails"
