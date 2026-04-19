"""Domain exception hierarchy for OEM worker Lambdas.

Extend FluxionError per worker module. Catch at the handler boundary and
decide whether to raise (poison-pill the message) or log-and-skip.
"""

from __future__ import annotations


class FluxionError(Exception):
    """Base class for all domain errors in fluxion-oem-processor.

    Attributes:
        code: Stable error code for structured logging and alerting.
        http_status: Approximate HTTP equivalent — used when logging severity.
    """

    code: str = "INTERNAL"
    http_status: int = 500


class DatabaseError(FluxionError):
    """Raised when a database operation fails unexpectedly."""

    code = "DATABASE_ERROR"
    http_status = 503


class TenantNotFound(FluxionError):
    """Raised when tenant_id has no matching schema in the mapping table."""

    code = "TENANT_NOT_FOUND"
    http_status = 404
