"""Domain exceptions for platform_resolver — copied from _template, no additions needed."""

from __future__ import annotations

from typing import Any


class FluxionError(Exception):
    """Base class for all Fluxion domain errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def to_appsync_error(self) -> dict[str, Any]:
        """Serialize to AppSync Lambda direct resolver error shape."""
        return {
            "errorType": self.code,
            "errorMessage": str(self) or self.code,
        }


class DatabaseError(FluxionError):
    """Database operation failed (connection, query, constraint)."""

    code = "DATABASE_ERROR"
    http_status = 503


class TenantNotFoundError(FluxionError):
    """Tenant id has no matching row in accesscontrol.tenants."""

    code = "TENANT_NOT_FOUND"
    http_status = 404


class NotFoundError(FluxionError):
    """Requested resource does not exist."""

    code = "NOT_FOUND"
    http_status = 404


class ForbiddenError(FluxionError):
    """Caller lacks a required permission."""

    code = "FORBIDDEN"
    http_status = 403


class AuthenticationError(FluxionError):
    """Identity claims missing or unresolvable."""

    code = "UNAUTHENTICATED"
    http_status = 401


class InvalidInputError(FluxionError):
    """Client-supplied input failed validation."""

    code = "INVALID_INPUT"
    http_status = 400


class UnknownFieldError(FluxionError):
    """GraphQL field name not registered in FIELD_HANDLERS."""

    code = "UNKNOWN_FIELD"
    http_status = 400
