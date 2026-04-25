"""Smoke tests for auth.py — build_context_from and permission_required decorator.

Uses unittest.mock to stub out DB calls; no real PostgreSQL needed.
Verifies the decorator dispatches with the correct (args, event, correlation_id)
signature and that ForbiddenError is raised on permission miss.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auth import build_context_from, permission_required
from exceptions import AuthenticationError, ForbiddenError, InvalidInputError


def _make_event(
    cognito_sub: str = "sub-123",
    tenant_id: str = "1",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "identity": {"claims": {"sub": cognito_sub, "custom:tenant_id": tenant_id}},
        "arguments": arguments or {},
    }


# ---------------------------------------------------------------------------
# build_context_from
# ---------------------------------------------------------------------------


def test_build_context_from_missing_identity_raises() -> None:
    with pytest.raises(AuthenticationError, match="missing identity claims"):
        build_context_from({})


def test_build_context_from_bad_tenant_id_raises() -> None:
    event = {"identity": {"claims": {"sub": "abc", "custom:tenant_id": "not-an-int"}}}
    with pytest.raises(InvalidInputError, match="not an integer"):
        build_context_from(event)


def test_build_context_from_resolves_context() -> None:
    """Happy path: stubs DB to return tenant + user; context fields match."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_schema_name.return_value = "dev1"

    # Patch _resolve_user_id and Database constructor
    with (
        patch("auth.Database", return_value=mock_db),
        patch("auth._resolve_user_id", return_value=42),
    ):
        ctx = build_context_from(_make_event(cognito_sub="sub-abc", tenant_id="7"))

    assert ctx.cognito_sub == "sub-abc"
    assert ctx.tenant_id == 7
    assert ctx.tenant_schema == "dev1"
    assert ctx.user_id == 42


# ---------------------------------------------------------------------------
# permission_required decorator
# ---------------------------------------------------------------------------


def _make_stub_db(has_permission_result: bool) -> MagicMock:
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get_schema_name.return_value = "dev1"
    mock_db.has_permission.return_value = has_permission_result
    return mock_db


def test_permission_required_calls_handler_on_grant() -> None:
    """Decorator calls wrapped handler with (args, ctx, correlation_id) on grant."""
    inner = MagicMock(return_value={"ok": True})
    decorated = permission_required("device:read")(inner)

    event = _make_event(arguments={"id": "d1"})
    mock_db = _make_stub_db(has_permission_result=True)

    with (
        patch("auth.Database", return_value=mock_db),
        patch("auth._resolve_user_id", return_value=99),
    ):
        result = decorated(event["arguments"], event, "corr-1")

    assert result == {"ok": True}
    args, ctx, cid = inner.call_args.args
    assert args == {"id": "d1"}
    assert ctx.tenant_schema == "dev1"
    assert cid == "corr-1"


def test_permission_required_raises_forbidden_on_miss() -> None:
    """Decorator raises ForbiddenError when has_permission returns False."""
    inner = MagicMock()
    decorated = permission_required("platform:admin")(inner)

    event = _make_event()
    mock_db = _make_stub_db(has_permission_result=False)

    with (
        patch("auth.Database", return_value=mock_db),
        patch("auth._resolve_user_id", return_value=1),
    ):
        with pytest.raises(ForbiddenError, match="platform:admin"):
            decorated(event["arguments"], event, "corr-2")

    inner.assert_not_called()
