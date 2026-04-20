"""Smoke tests for the _template Lambda handler.

These tests verify the skeleton behaves correctly before a real Lambda
is implemented. Replace with field-specific tests when scaffolding.
"""

from __future__ import annotations

import pytest
from handler import lambda_handler


def test_handler_raises_not_implemented() -> None:
    """Template handler must raise NotImplementedError — it is not deployable."""
    with pytest.raises(NotImplementedError):
        lambda_handler({}, None)
