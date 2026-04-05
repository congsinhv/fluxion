"""Utility functions for upload_processor."""

import re


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only) to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError("Invalid tenant_id format")
    return tenant_id
