"""Custom exceptions for checkin_handler."""


class FluxionError(Exception):
    """Base exception with error_type for structured error reporting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class ExecutionNotFoundError(FluxionError):
    def __init__(self, command_uuid: str):
        super().__init__(f"Execution not found for command_uuid {command_uuid}", "EXECUTION_NOT_FOUND")


class UnknownEventTypeError(FluxionError):
    def __init__(self, event_type: str):
        super().__init__(f"Unknown event type: {event_type}", "UNKNOWN_EVENT_TYPE")
