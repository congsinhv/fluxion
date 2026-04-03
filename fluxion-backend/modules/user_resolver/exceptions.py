"""Custom exceptions for user_resolver."""


class FluxionError(Exception):
    """Base exception with error_type for AppSync error formatting."""

    def __init__(self, message: str, error_type: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class UserNotFoundError(FluxionError):
    def __init__(self, user_id: str):
        super().__init__(f"User {user_id} not found", "USER_NOT_FOUND")


class ForbiddenError(FluxionError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "FORBIDDEN")


class UserAlreadyExistsError(FluxionError):
    def __init__(self, email: str):
        super().__init__(f"User with email {email} already exists", "USER_ALREADY_EXISTS")
