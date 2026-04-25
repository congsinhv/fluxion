"""Environment variables and logger — single source of truth for user_resolver."""

from __future__ import annotations

import logging
import os

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
POWERTOOLS_SERVICE_NAME: str = os.environ.get("POWERTOOLS_SERVICE_NAME", "user_resolver")

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}',
)
logger: logging.Logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

# Required at Lambda cold start; empty default lets unit tests import without a real DB.
DATABASE_URI: str = os.environ.get("DATABASE_URI", "")

# Cognito user pool for admin operations (AdminCreateUser, AdminDeleteUser, etc.)
COGNITO_USER_POOL_ID: str = os.environ.get("COGNITO_USER_POOL_ID", "")
