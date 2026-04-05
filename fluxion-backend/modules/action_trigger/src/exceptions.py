"""Custom exceptions for action_trigger."""


class FluxionError(Exception):
    """Base exception with error_type for structured error reporting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class DeviceTokensNotFoundError(FluxionError):
    def __init__(self, device_id: str):
        super().__init__(f"Device tokens not found for {device_id}", "DEVICE_TOKENS_NOT_FOUND")
