"""Domain exceptions for Lambda resolvers.

All errors extend ``FluxionError`` so the handler boundary catches one type
and maps to AppSync error responses consistently (design-patterns.md §4).

``to_appsync_error()`` on the base produces ``{"errorType", "errorMessage"}``
as expected by AppSync Lambda direct resolvers.

Add Lambda-specific subclasses here when scaffolding a real Lambda from
this template (copy the file; do not import across Lambda boundaries).
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
    """Database operation failed (connection, query, constraint).

    Maps to HTTP 503 — the service is degraded but the request was valid.
    """

    code = "DATABASE_ERROR"
    http_status = 503


class TenantNotFoundError(FluxionError):
    """Tenant id has no matching row in ``accesscontrol.tenants``.

    Args:
        tenant_id: The tenant identifier that could not be resolved.
    """

    code = "TENANT_NOT_FOUND"
    http_status = 404


class NotFoundError(FluxionError):
    """Requested resource does not exist.

    Args:
        resource: Human-readable resource description (e.g. ``"device abc123"``).
    """

    code = "NOT_FOUND"
    http_status = 404


class ForbiddenError(FluxionError):
    """Caller lacks a required permission.

    Raised by ``permission_required`` decorator when ``has_permission``
    returns False. Never expose internal details in the message.
    """

    code = "FORBIDDEN"
    http_status = 403


class AuthenticationError(FluxionError):
    """Identity claims missing or unresolvable.

    Raised when Cognito claims are absent, malformed, or the cognito_sub
    has no matching row in ``accesscontrol.users``.
    """

    code = "UNAUTHENTICATED"
    http_status = 401


class InvalidInputError(FluxionError):
    """Client-supplied input failed validation.

    Raised for business-rule violations that Pydantic does not cover
    (e.g. a referenced entity does not exist, an enum value out of range
    for the current state). For schema-level validation failures Pydantic
    raises ``ValidationError`` — convert it to this at the handler boundary.
    """

    code = "INVALID_INPUT"
    http_status = 400


class UnknownFieldError(FluxionError):
    """GraphQL field name not registered in ``FIELD_HANDLERS``.

    Raised by the handler dispatch when ``event["info"]["fieldName"]``
    has no entry in the dispatch table.
    """

    code = "UNKNOWN_FIELD"
    http_status = 400


def to_appsync_error(exc: FluxionError) -> dict[str, Any]:
    """Functional alias for ``exc.to_appsync_error()``.

    Provided as a free function so callsites that already have a reference
    to the exception type can call it without holding the instance.

    Args:
        exc: Any ``FluxionError`` subclass instance.

    Returns:
        ``{"errorType": <code>, "errorMessage": <message>}`` dict.
    """
    return exc.to_appsync_error()
