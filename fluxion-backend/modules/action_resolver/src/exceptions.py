"""Custom exceptions for action_resolver."""


class FluxionError(Exception):
    """Base exception with error_type for AppSync error formatting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class DeviceNotFoundError(FluxionError):
    def __init__(self, device_id: str):
        super().__init__(f"Device {device_id} not found", "DEVICE_NOT_FOUND")


class ActionNotFoundError(FluxionError):
    def __init__(self, action_id: str):
        super().__init__(f"Action {action_id} not found", "ACTION_NOT_FOUND")


class DeviceBusyError(FluxionError):
    def __init__(self, device_id: str):
        super().__init__(f"Device {device_id} is busy", "DEVICE_BUSY")


class InvalidTransitionError(FluxionError):
    def __init__(self, device_state_id: int, action_name: str):
        super().__init__(
            f"Invalid transition: device in state {device_state_id}, action '{action_name}' not applicable",
            "INVALID_TRANSITION",
        )
