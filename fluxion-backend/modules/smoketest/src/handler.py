"""Smoketest Lambda handler — proves the CI ECR-push matrix end-to-end."""

from typing import Any


def lambda_handler(_event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Return a static payload; used only to verify deploy pipeline."""
    return {"statusCode": 200, "body": "smoketest ok"}
