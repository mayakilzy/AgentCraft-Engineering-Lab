"""Standard error model and exception classes.

All API errors share the shape `{code, message, details?, request_id}` per
`02_ARCHITECTURE_AND_CONTRACTS.md` §4. Status codes follow the contract:
400 malformed, 401 guest missing, 403 cross-session, 404 unknown,
409 invalid state, 422 validation, 429 quota, 503 unavailable service.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# Map contract status codes to short stable error codes.
_DEFAULT_CODE: Dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "invalid_state",
    422: "validation_error",
    429: "quota_exceeded",
    503: "service_unavailable",
}


def _request_id(request: Request | None) -> str:
    """Stable per-request id for correlation; falls back to a fresh UUID."""
    if request is None:
        return str(uuid.uuid4())
    return request.headers.get("x-request-id") or str(uuid.uuid4())


class AppError(Exception):
    """Base application error. Subclass for typed contract codes."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        status_code: int | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class InvalidStateError(AppError):
    status_code = 409
    code = "invalid_state"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


def _error_body(
    code: str,
    message: str,
    request: Request | None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": _request_id(request),
    }
    if details:
        body["details"] = details
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, request, exc.details),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _DEFAULT_CODE.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, str(exc.detail), request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(
            "validation_error",
            "Request validation failed",
            request,
            {"errors": exc.errors()},
        ),
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Avoid leaking internal details; structured logs carry the traceback.
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "internal_error", "An unexpected error occurred.", request
        ),
    )
