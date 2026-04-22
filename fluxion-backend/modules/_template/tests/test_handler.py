"""Smoke tests for the _template Lambda handler dispatch shape.

Verifies the skeleton behaves correctly before a real Lambda is scaffolded:
  - Unknown field → FluxionError-mapped AppSync error response (not exception).
  - Registered handler is dispatched and its return value is passed through.
  - Missing info/fieldName key returns an error response (not exception).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from handler import FIELD_HANDLERS, lambda_handler


def _make_event(field: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"info": {"fieldName": field}, "arguments": arguments or {}}


def test_unknown_field_returns_appsync_error() -> None:
    """Unknown field name → UNKNOWN_FIELD error dict, no exception raised."""
    result = lambda_handler(_make_event("noSuchField"), MagicMock(aws_request_id="test-1"))
    assert result["errorType"] == "UNKNOWN_FIELD"
    assert "noSuchField" in result["errorMessage"]


def test_missing_field_name_returns_error() -> None:
    """Event with no info.fieldName → UNKNOWN_FIELD error, no exception."""
    result = lambda_handler({}, MagicMock(aws_request_id="test-2"))
    assert result["errorType"] == "UNKNOWN_FIELD"


def test_registered_handler_is_dispatched() -> None:
    """A registered handler is called and its return value passed through."""
    expected: dict[str, Any] = {"id": "abc", "state": "active"}
    mock_handler = MagicMock(return_value=expected)

    FIELD_HANDLERS["_testField"] = mock_handler
    try:
        result = lambda_handler(_make_event("_testField", {"x": 1}), MagicMock(aws_request_id="test-3"))
    finally:
        del FIELD_HANDLERS["_testField"]

    assert result == expected
    mock_handler.assert_called_once()


def test_handler_catches_fluxion_error() -> None:
    """Handler that raises FluxionError → error dict, no exception propagated."""
    from exceptions import NotFoundError

    def _raise(_args: Any, _event: Any, _cid: str) -> Any:
        raise NotFoundError("thing xyz")

    FIELD_HANDLERS["_errorField"] = _raise
    try:
        result = lambda_handler(_make_event("_errorField"), MagicMock(aws_request_id="test-4"))
    finally:
        del FIELD_HANDLERS["_errorField"]

    assert result["errorType"] == "NOT_FOUND"
    assert "thing xyz" in result["errorMessage"]
