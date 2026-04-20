"""Shared pytest fixtures for the _template Lambda tests.

The autouse session fixture sets the minimum env vars required so that
importing config.py does not fail during collection. Real integration tests
should override these with actual values or use testcontainers.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _set_env() -> None:
    """Set required environment variables for the test session.

    Uses setdefault so that values provided by CI/CD or testcontainers
    are not overwritten.
    """
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "_template-test")
    os.environ.setdefault("DATABASE_URI", "postgresql://localhost/test")
