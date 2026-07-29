"""Explicit domain errors mapped to safe API responses."""

from http import HTTPStatus


class AppError(Exception):
    """Expected application failure with a stable public code."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    """Requested in-memory entity does not exist."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, HTTPStatus.NOT_FOUND)


class ConflictError(AppError):
    """Request conflicts with current draft state or version."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, HTTPStatus.CONFLICT)


class RequestValidationError(AppError):
    """Syntactically valid request violates a workflow rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, HTTPStatus.UNPROCESSABLE_ENTITY)
