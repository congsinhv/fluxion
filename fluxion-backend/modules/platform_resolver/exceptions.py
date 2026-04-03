"""Custom exceptions for platform_resolver."""


class FluxionError(Exception):
    """Base exception with error_type for AppSync error formatting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class NotFoundError(FluxionError):
    def __init__(self, entity: str, entity_id):
        super().__init__(f"{entity} {entity_id} not found", f"{entity.upper()}_NOT_FOUND")


class ForbiddenError(FluxionError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "FORBIDDEN")
