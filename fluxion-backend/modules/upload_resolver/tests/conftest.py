"""Shared pytest fixtures for upload_resolver Lambda tests.

The autouse session fixture sets the minimum env vars required so that
importing config.py does not fail during collection. No real DB or SQS needed.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _set_env() -> None:
    """Set required environment variables for the test session."""
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "upload_resolver-test")
    os.environ.setdefault("DATABASE_URI", "postgresql://localhost/test")
    os.environ.setdefault(
        "UPLOAD_PROCESSOR_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/000000000000/upload-processor-test",
    )
