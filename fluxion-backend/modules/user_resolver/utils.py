"""Pagination and response formatting utilities for user_resolver."""

import base64
import json
import re

from config import logger


def decode_next_token(next_token: str | None) -> int:
    """Decode base64 nextToken to offset. Returns 0 if None/invalid."""
    if not next_token:
        return 0
    try:
        decoded = json.loads(base64.b64decode(next_token))
        return decoded.get("offset", 0)
    except Exception:
        logger.warning(f"Invalid nextToken: {next_token}")
        return 0


def encode_next_token(offset: int) -> str:
    """Encode offset to base64 nextToken."""
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only)."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError(f"Invalid tenant_id format: {tenant_id}")
    return tenant_id


def format_user(row: dict) -> dict:
    """Format a user row for GraphQL response."""
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "name": row["name"],
        "role": row["role"].upper(),
        "isActive": row["is_active"],
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
    }
