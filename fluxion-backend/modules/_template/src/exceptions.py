"""Domain exceptions for this Lambda.

All errors extend FluxionError so the handler boundary can catch one type
and map to AppSync error responses consistently (design-patterns.md §4).
Add Lambda-specific subclasses here when scaffolding a real Lambda.
"""

from __future__ import annotations

from typing import Any


class FluxionError(Exception):
    """Base class for all Fluxion domain errors.

    Extend this per Lambda. The handler catches FluxionError and calls
    `to_appsync_error()` to produce a well-shaped GraphQL error response.

    Args:
        message: Human-readable error description.
    """

    code: str = "INTERNAL"
    http_status: int = 500

    def to_appsync_error(self) -> dict[str, Any]:
        """Serialize to AppSync error response shape.

        Returns:
            Dict with ``errorType`` and ``message`` keys expected by AppSync.
        """
        return {"errorType": self.code, "message": str(self) or self.code}


class DatabaseError(FluxionError):
    """Raised when a database operation fails (connection, query, constraint).

    Maps to HTTP 503 — the service is degraded but the request itself was valid.
    """

    code = "DATABASE_ERROR"
    http_status = 503


class TenantNotFoundError(FluxionError):
    """Raised when tenant_id has no matching row in t_tenant_schema_mapping.

    Args:
        tenant_id: The tenant identifier that could not be resolved.
    """

    code = "TENANT_NOT_FOUND"
    http_status = 404
