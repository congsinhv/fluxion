"""Custom exceptions for device_resolver."""


class FluxionError(Exception):
    """Base exception with error_type for AppSync error formatting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class DeviceNotFoundError(FluxionError):
    def __init__(self, device_id: str):
        super().__init__(f"Device {device_id} not found", "DEVICE_NOT_FOUND")
