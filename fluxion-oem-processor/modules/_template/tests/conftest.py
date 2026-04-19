"""Pytest configuration and shared fixtures for _template tests.

Env vars are set via pytest_configure (runs before module collection) so that
config.py's module-level `os.environ["DATABASE_URI"]` never raises at import.
"""

from __future__ import annotations

import os


def pytest_configure() -> None:
    """Seed required env vars before any source module is imported/collected."""
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "_template-test")
    # Dummy URI for unit tests; real integration tests override with a live DB.
    os.environ.setdefault("DATABASE_URI", "postgresql://user:pass@localhost/test")
