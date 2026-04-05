"""Custom exceptions for upload_resolver."""


class FluxionError(Exception):
    """Base exception with error_type for AppSync error formatting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type
