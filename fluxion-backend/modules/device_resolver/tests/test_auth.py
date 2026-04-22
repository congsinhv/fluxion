"""Unit tests for auth.py — mocks Database, tests context extraction paths."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auth import Context, build_context_from
from exceptions import AuthenticationError, InvalidInputError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUB = "cognito-sub-abc"
TENANT_ID = 1
SCHEMA = "dev1"
USER_ID = 42

_VALID_CLAIMS: dict[str, Any] = {
    "sub": SUB,
    "custom:tenant_id": str(TENANT_ID),
}

_VALID_EVENT: dict[str, Any] = {
    "identity": {"claims": _VALID_CLAIMS},
    "info": {"fieldName": "getDevice"},
    "arguments": {},
}


def _mock_db_for_context(schema: str = SCHEMA, user_id: int = USER_ID) -> MagicMock:
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_schema_name.return_value = schema
    # Simulate _resolve_user_id via _require_conn + cursor
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = {"id": user_id}
    mock_conn.cursor.return_value = mock_cur
    mock_db._require_conn.return_value = mock_conn  # noqa: SLF001
    return mock_db


# ---------------------------------------------------------------------------
# build_context_from — happy path
# ---------------------------------------------------------------------------


def test_build_context_from_happy_path() -> None:
    mock_db = _mock_db_for_context()
    with patch("auth.Database", return_value=mock_db):
        ctx = build_context_from(_VALID_EVENT)

    assert isinstance(ctx, Context)
    assert ctx.cognito_sub == SUB
    assert ctx.tenant_id == TENANT_ID
    assert ctx.tenant_schema == SCHEMA
    assert ctx.user_id == USER_ID


# ---------------------------------------------------------------------------
# build_context_from — missing identity block
# ---------------------------------------------------------------------------


def test_build_context_from_missing_identity() -> None:
    event: dict[str, Any] = {"identity": {}, "info": {}, "arguments": {}}
    with pytest.raises(AuthenticationError, match="missing identity claims"):
        build_context_from(event)


def test_build_context_from_missing_sub() -> None:
    event: dict[str, Any] = {
        "identity": {"claims": {"custom:tenant_id": "1"}},
        "info": {},
        "arguments": {},
    }
    with pytest.raises(AuthenticationError):
        build_context_from(event)


def test_build_context_from_bad_tenant_id() -> None:
    event: dict[str, Any] = {
        "identity": {"claims": {"sub": SUB, "custom:tenant_id": "not-an-int"}},
        "info": {},
        "arguments": {},
    }
    with pytest.raises(InvalidInputError, match="custom:tenant_id"):
        build_context_from(event)


# ---------------------------------------------------------------------------
# build_context_from — user not found in accesscontrol.users
# ---------------------------------------------------------------------------


def test_build_context_from_user_not_found() -> None:
    mock_db = _mock_db_for_context()
    # Make _resolve_user_id return no row
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = None  # no user row
    mock_conn.cursor.return_value = mock_cur
    mock_db._require_conn.return_value = mock_conn  # noqa: SLF001

    with patch("auth.Database", return_value=mock_db):
        with pytest.raises(AuthenticationError, match="no user"):
            build_context_from(_VALID_EVENT)
