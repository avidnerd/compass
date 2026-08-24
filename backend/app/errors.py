"""Stable error codes and the v1 error envelope."""
from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class ProviderError(Exception):
    """A connected-data provider failed. Codes are safe and redacted — raw
    provider payloads must never reach this exception."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def not_found(resource: str = "resource") -> ApiError:
    return ApiError(404, "not_found", f"The requested {resource} was not found.")


def forbidden(message: str = "You do not have access to this resource.") -> ApiError:
    return ApiError(403, "forbidden", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def invalid(message: str, details: Any = None) -> ApiError:
    return ApiError(422, "invalid_request", message, details)


def upstream(code: str, message: str) -> ApiError:
    return ApiError(502, code, message)
