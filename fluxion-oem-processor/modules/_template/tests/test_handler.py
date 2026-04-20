"""Smoke tests for the _template Lambda handler.

These tests verify the scaffold contract: the handler is importable, rejects
empty invocations with NotImplementedError, and iterates SQS records correctly.
"""

from __future__ import annotations

from typing import Any

import pytest
from handler import lambda_handler


class _FakeContext:
    """Minimal stand-in for the AWS Lambda context object."""

    aws_request_id: str = "test-request-id"


def test_handler_raises_not_implemented_on_non_empty_batch() -> None:
    """Handler must raise NotImplementedError for each SQS record in the batch."""
    event: dict[str, Any] = {
        "Records": [
            {"body": '{"action": "test"}', "receiptHandle": "abc123"},
        ]
    }
    with pytest.raises(NotImplementedError):
        lambda_handler(event, _FakeContext())


def test_handler_no_records_completes_without_error() -> None:
    """Handler with an empty Records list completes without error (no-op batch)."""
    event: dict[str, Any] = {"Records": []}
    lambda_handler(event, _FakeContext())  # must not raise


def test_handler_missing_records_key_completes_without_error() -> None:
    """Handler tolerates missing Records key — SQS always provides it but be safe."""
    lambda_handler({}, _FakeContext())  # must not raise
