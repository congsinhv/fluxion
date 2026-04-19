"""Environment variable bindings and logger initialisation for this Lambda.

All other modules import `logger` from here. Keep this file minimal —
one source of truth for runtime configuration.
"""

from __future__ import annotations

import logging
import os

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
POWERTOOLS_SERVICE_NAME: str = os.environ.get("POWERTOOLS_SERVICE_NAME", "_template")

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}',
)
logger: logging.Logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

# Database connection string — required at runtime. Fails loud at Lambda cold
# start (KeyError) rather than silently passing an empty string to SQLAlchemy.
# Rename / remove variables that do not apply to the concrete worker.
DATABASE_URI: str = os.environ["DATABASE_URI"]
# SQS_QUEUE_URL: str = os.environ["SQS_QUEUE_URL"]  # uncomment when needed
