"""Custom exceptions for upload_processor."""


class FluxionError(Exception):
    """Base exception with error_type for structured error reporting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type
