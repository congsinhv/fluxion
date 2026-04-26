"""Domain exceptions for upload_resolver Lambda.

All errors extend ``FluxionError`` so the handler boundary catches one type
and maps to AppSync error responses consistently (design-patterns.md §4).

``to_appsync_error()`` on the base produces ``{"errorType", "errorMessage"}``
as expected by AppSync Lambda direct resolvers.
"""

from __future__ import annotations

from typing import Any


class FluxionError(Exception):
    """Base class for all Fluxion domain errors.

    Subclasses set ``code`` and ``http_status`` as class attributes.
    The handler catches ``FluxionError`` and calls ``to_appsync_error()``.

    Args:
        message: Human-readable error description.
    """

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def to_appsync_error(self) -> dict[str, Any]:
        """Serialize to AppSync Lambda direct resolver error shape.

        Returns:
            ``{"errorType": <code>, "errorMessage": <message>}`` dict.
        """
        return {
            "errorType": self.code,
            "errorMessage": str(self) or self.code,
        }


class DatabaseError(FluxionError):
    """Database operation failed (connection, query, constraint)."""

    code = "DATABASE_ERROR"
    http_status = 503


class TenantNotFoundError(FluxionError):
    """Tenant id has no matching row in ``accesscontrol.tenants``."""

    code = "TENANT_NOT_FOUND"
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
    """GraphQL field name not registered in ``FIELD_HANDLERS``."""

    code = "UNKNOWN_FIELD"
    http_status = 400


class SqsError(FluxionError):
    """SQS SendMessage failed.

    Raised by ``sqs.py``; callers log and suppress after the dedupe decision
    so the request succeeds (fire-and-forget after the validation commit point).
    """

    code = "SQS_ERROR"
    http_status = 503


def to_appsync_error(exc: FluxionError) -> dict[str, Any]:
    """Functional alias for ``exc.to_appsync_error()``.

    Args:
        exc: Any ``FluxionError`` subclass instance.

    Returns:
        ``{"errorType": <code>, "errorMessage": <message>}`` dict.
    """
    return exc.to_appsync_error()
