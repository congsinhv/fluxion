"""Environment variables and logger — single source of truth for this Lambda.

All handlers and services import `logger` (and any env var constants) from here.
They never call `os.environ` directly (see design-patterns.md §4).
"""

from __future__ import annotations

import logging
import os

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
POWERTOOLS_SERVICE_NAME: str = os.environ.get("POWERTOOLS_SERVICE_NAME", "_template")

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}',
)
logger: logging.Logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

# ---------------------------------------------------------------------------
# Required environment variables (uncomment + rename per Lambda)
# ---------------------------------------------------------------------------
# DATABASE_URI must be set for any Lambda that uses db.py.
# Using a safe default here so mypy and unit tests can import config without
# a real DB present. Real Lambdas must always inject DATABASE_URI via env.
DATABASE_URI: str = os.environ.get("DATABASE_URI", "")

# When scaffolding a real Lambda, add required env vars below this line.
# Pattern: VAR = os.environ["VAR_NAME"]  (fails at cold start if missing, not mid-request)
# See design-patterns.md §4 for the config.py pattern.
