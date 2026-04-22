"""Unit tests for user_resolver handler — happy paths + permission checks.

Connection sequence per handler call:
  conn #0 (build_context_from):  query 1 = get_schema_name, query 2 = _resolve_user_id
  conn #1 (permission_required): query 1 = has_permission
  conn #2+ (field handler):      actual business queries

Each psycopg.connect call is mocked independently; within a single connection
multiple sequential fetchone calls are handled via side_effect lists.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

NOW = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)

USER_ROW = {
    "id": 1,
    "email": "alice@example.com",
    "cognito_sub": "sub-alice",
    "name": "Alice",
    "enabled": True,
    "created_at": NOW,
}

USER_ROW_2 = {
    "id": 2,
    "email": "bob@example.com",
    "cognito_sub": "sub-bob",
    "name": "Bob",
    "enabled": True,
    "created_at": NOW,
}

COGNITO_ATTRS = {"sub": "sub-alice", "custom:role": "ADMIN"}
COGNITO_ATTRS_2 = {"sub": "sub-bob", "custom:role": "OPERATOR"}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_conn(fetchone_seq: list[Any], fetchall_val: list[Any] | None = None) -> MagicMock:
    """Return a mock psycopg connection whose cursor.fetchone cycles through fetchone_seq."""
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


def _make_event(field: str, args: dict[str, Any], cognito_sub: str = "sub-alice") -> dict[str, Any]:
    return {
        "info": {"fieldName": field},
        "arguments": args,
        "identity": {
            "claims": {
                "sub": cognito_sub,
                "custom:tenant_id": "1",
            }
        },
    }


class FakeLambdaContext:
    aws_request_id = "test-correlation-id"


# ---------------------------------------------------------------------------
# Standard auth connections builder
# conn#0 = build_context_from (schema_name + user_id_lookup on same conn)
# conn#1 = permission check
# conn#2+ = handler-specific
# ---------------------------------------------------------------------------

def _auth_connections(perm_row: Any, *handler_conns: MagicMock) -> list[MagicMock]:
    """Return ordered list of mock connections for a typical handler call.

    conn#0: build_context_from — fetchone returns schema_row then user_id_row
    conn#1: permission check   — fetchone returns perm_row (truthy = allowed)
    conn#2+: handler-specific connections
    """
    conn0 = _make_conn(
        fetchone_seq=[{"schema_name": "dev1"}, {"id": 1}]
    )
    conn1 = _make_conn(fetchone_seq=[perm_row])
    return [conn0, conn1, *handler_conns]


# ---------------------------------------------------------------------------
# getCurrentUser
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    def test_happy_path(self) -> None:
        """getCurrentUser returns UserResponse with role from Cognito."""
        from handler import lambda_handler

        conn_query = _make_conn(fetchone_seq=[USER_ROW])
        conns = _auth_connections({"1": 1}, conn_query)

        event = _make_event("getCurrentUser", {})

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_get_user", return_value=COGNITO_ATTRS):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["email"] == "alice@example.com"
        assert result["role"] == "ADMIN"
        assert result["isActive"] is True
        assert result["id"] == "1"

    def test_missing_identity_returns_unauthenticated(self) -> None:
        """Event without identity block returns UNAUTHENTICATED."""
        from handler import lambda_handler

        event: dict[str, Any] = {
            "info": {"fieldName": "getCurrentUser"},
            "arguments": {},
        }
        result = lambda_handler(event, FakeLambdaContext())
        assert result["errorType"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
# getUser
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_happy_path(self) -> None:
        """getUser(id) returns UserResponse."""
        from handler import lambda_handler

        conn_query = _make_conn(fetchone_seq=[USER_ROW])
        conns = _auth_connections({"1": 1}, conn_query)

        event = _make_event("getUser", {"id": "1"})

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_get_user", return_value=COGNITO_ATTRS):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["email"] == "alice@example.com"
        assert result["role"] == "ADMIN"

    def test_invalid_id_returns_error(self) -> None:
        """getUser with non-integer id returns INVALID_INPUT."""
        from handler import lambda_handler

        conns = _auth_connections({"1": 1})
        event = _make_event("getUser", {"id": "not-a-number"})

        with patch("psycopg.connect", side_effect=conns):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# listUsers
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_non_admin_forbidden(self) -> None:
        """listUsers without user:read permission returns FORBIDDEN."""
        from handler import lambda_handler

        # perm_row=None → has_permission returns False → FORBIDDEN
        conns = _auth_connections(None)
        event = _make_event("listUsers", {})

        with patch("psycopg.connect", side_effect=conns):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "FORBIDDEN"

    def test_happy_path_returns_connection(self) -> None:
        """listUsers returns UserConnection with items and nextToken when limit == len(rows)."""
        from handler import lambda_handler

        # list_users uses fetchall, not fetchone
        conn_query = _make_conn(fetchone_seq=[], fetchall_val=[USER_ROW, USER_ROW_2])
        conns = _auth_connections({"1": 1}, conn_query)

        event = _make_event("listUsers", {"limit": 2})

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_get_user", side_effect=[COGNITO_ATTRS, COGNITO_ATTRS_2]):
            result = lambda_handler(event, FakeLambdaContext())

        assert "items" in result
        assert len(result["items"]) == 2
        # limit == rows returned → nextToken set
        assert result["nextToken"] is not None

    def test_returns_no_next_token_when_exhausted(self) -> None:
        """nextToken is None when fewer rows than limit are returned."""
        from handler import lambda_handler

        conn_query = _make_conn(fetchone_seq=[], fetchall_val=[USER_ROW])
        conns = _auth_connections({"1": 1}, conn_query)

        event = _make_event("listUsers", {"limit": 20})

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_get_user", return_value=COGNITO_ATTRS):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["nextToken"] is None


# ---------------------------------------------------------------------------
# createUser
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_happy_path(self) -> None:
        """createUser with admin permission creates Cognito user + DB row."""
        from handler import lambda_handler

        # conn#2 = create_user_placeholder RETURNING id
        conn_placeholder = _make_conn(fetchone_seq=[{"id": 7}])
        # conn#3 = set_user_cognito_sub + get_user_by_id share one Database context
        conn_set_and_get = _make_conn(fetchone_seq=[{"id": 7}, USER_ROW])
        conns = _auth_connections({"1": 1}, conn_placeholder, conn_set_and_get)

        event = _make_event("createUser", {
            "input": {"email": "alice@example.com", "name": "Alice", "role": "ADMIN"}
        })

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_create_user", return_value="sub-alice"), \
             patch("cognito.admin_update_user_attributes"):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["email"] == "alice@example.com"
        assert result["role"] == "ADMIN"
        assert "errorType" not in result

    def test_non_admin_forbidden(self) -> None:
        """createUser without user:admin permission returns FORBIDDEN."""
        from handler import lambda_handler

        conns = _auth_connections(None)
        event = _make_event("createUser", {
            "input": {"email": "x@example.com", "name": "X", "role": "OPERATOR"}
        })

        with patch("psycopg.connect", side_effect=conns):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# updateUser patch semantics
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_patch_semantics_name_only(self) -> None:
        """updateUser with only name field updates name; role unchanged."""
        from handler import lambda_handler

        updated_row = {**USER_ROW, "name": "Alice Updated"}
        conn_query = _make_conn(fetchone_seq=[updated_row])
        conns = _auth_connections({"1": 1}, conn_query)

        event = _make_event("updateUser", {"id": "1", "input": {"name": "Alice Updated"}})

        with patch("psycopg.connect", side_effect=conns), \
             patch("cognito.admin_get_user", return_value=COGNITO_ATTRS):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["name"] == "Alice Updated"
        assert "errorType" not in result

    def test_no_fields_returns_error(self) -> None:
        """updateUser with empty input returns INVALID_INPUT."""
        from handler import lambda_handler

        conns = _auth_connections({"1": 1})
        event = _make_event("updateUser", {"id": "1", "input": {}})

        with patch("psycopg.connect", side_effect=conns):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "INVALID_INPUT"

    def test_invalid_id_returns_error(self) -> None:
        """updateUser with non-integer id returns INVALID_INPUT."""
        from handler import lambda_handler

        conns = _auth_connections({"1": 1})
        event = _make_event("updateUser", {"id": "bad", "input": {"name": "X"}})

        with patch("psycopg.connect", side_effect=conns):
            result = lambda_handler(event, FakeLambdaContext())

        assert result["errorType"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Unknown field
# ---------------------------------------------------------------------------

class TestUnknownField:
    def test_unknown_field_returns_error(self) -> None:
        """Lambda returns UNKNOWN_FIELD for unregistered GraphQL fields."""
        from handler import lambda_handler

        event: dict[str, Any] = {
            "info": {"fieldName": "deleteUser"},
            "arguments": {},
            "identity": {"claims": {"sub": "x", "custom:tenant_id": "1"}},
        }

        result = lambda_handler(event, FakeLambdaContext())
        assert result["errorType"] == "UNKNOWN_FIELD"
