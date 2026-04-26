"""Domain exceptions for action_resolver Lambda.

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
    """GraphQL field name not registered in ``FIELD_HANDLERS``."""

    code = "UNKNOWN_FIELD"
    http_status = 400


# ---------------------------------------------------------------------------
# Action-resolver-specific errors
# ---------------------------------------------------------------------------


class ActionNotFoundError(FluxionError):
    """Requested action does not exist in the tenant schema.

    Raised before the per-device loop so the whole request fails fast.
    """

    code = "ACTION_NOT_FOUND"
    http_status = 404


class TemplateNotFoundError(FluxionError):
    """messageTemplateId references a template that does not exist.

    Raised before the per-device loop; whole-request failure.
    """

    code = "TEMPLATE_NOT_FOUND"
    http_status = 404


class TemplateArchivedError(FluxionError):
    """Template exists but ``is_active = FALSE`` — cannot be used.

    Raised before the per-device loop; whole-request failure.
    """

    code = "TEMPLATE_ARCHIVED"
    http_status = 422


class InvalidStateError(FluxionError):
    """Device state does not match ``action.from_state_id`` (FSM violation).

    Per-device failure for ``assignAction``.
    Encoded as reason string in ``BulkAssignError`` for bulk path.
    """

    code = "INVALID_TRANSITION"
    http_status = 422


class DeviceAlreadyAssignedError(FluxionError):
    """Device already has an assigned action (race-safe detection post-UPDATE).

    Per-device failure for ``assignAction``.
    Encoded as reason string in ``BulkAssignError`` for bulk path.
    """

    code = "DEVICE_BUSY"
    http_status = 409


class SqsError(FluxionError):
    """SQS SendMessage failed.

    Raised by ``sqs.py``; callers log and suppress after DB commit so the
    request succeeds and rows remain PENDING for the action-trigger consumer
    to surface via ActionLog error reporting (P1b).
    """

    code = "SQS_ERROR"
    http_status = 503


class BatchNotFoundError(FluxionError):
    """Batch UUID does not exist in ``batch_actions``.

    Used by ``generateActionLogErrorReport`` when no batch row is found.
    """

    code = "BATCH_NOT_FOUND"
    http_status = 404


class S3Error(FluxionError):
    """S3 operation failed (PutObject or presign).

    Raised by ``s3.py``; callers should surface to AppSync as INTERNAL_ERROR.
    """

    code = "S3_ERROR"
    http_status = 503


def to_appsync_error(exc: FluxionError) -> dict[str, Any]:
    """Functional alias for ``exc.to_appsync_error()``.

    Args:
        exc: Any ``FluxionError`` subclass instance.

    Returns:
        ``{"errorType": <code>, "errorMessage": <message>}`` dict.
    """
    return exc.to_appsync_error()
