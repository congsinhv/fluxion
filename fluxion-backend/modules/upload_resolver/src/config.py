"""Environment variables and logger — single source of truth for upload_resolver Lambda.

All handlers and services import `logger` (and any env var constants) from here.
Never call `os.environ` directly in other modules (see design-patterns.md §4).
"""

from __future__ import annotations

import logging
import os

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
POWERTOOLS_SERVICE_NAME: str = os.environ.get("POWERTOOLS_SERVICE_NAME", "upload_resolver")

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}',
)
logger: logging.Logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------

# DATABASE_URI must be set for any Lambda that uses db.py.
# Safe default so unit tests can import config without a real DB present.
DATABASE_URI: str = os.environ.get("DATABASE_URI", "")

# UPLOAD_PROCESSOR_QUEUE_URL is the SQS queue URL for the upload-processor consumer.
# Must be injected at Lambda cold start; empty string is safe for unit tests.
UPLOAD_PROCESSOR_QUEUE_URL: str = os.environ.get("UPLOAD_PROCESSOR_QUEUE_URL", "")
