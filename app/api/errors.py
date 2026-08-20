"""Application-wide API error translation and response handling."""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.error import ErrorBody, ErrorResponse, ValidationErrorDetail
from app.services.auth_service import (
    AuthenticationError,
    DuplicateEmailError,
    InvalidRefreshTokenError,
)
from app.services.ticket_service import TicketNotFoundError, TicketStateError
from app.services.webhook_service import WebhookNotFoundError

logger = logging.getLogger(__name__)


class APIException(HTTPException):
    """HTTP exception carrying a stable public error code."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=message,
            headers=dict(headers) if headers is not None else None,
        )
        self.code = code


COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}

_DEFAULT_HTTP_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    422: "VALIDATION_ERROR",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def register_exception_handlers(app: FastAPI) -> None:
    """Register common and domain-specific exception handlers."""

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(InvalidRefreshTokenError, invalid_refresh_token_handler)
    app.add_exception_handler(AuthenticationError, authentication_error_handler)
    app.add_exception_handler(DuplicateEmailError, duplicate_email_handler)
    app.add_exception_handler(TicketNotFoundError, ticket_not_found_handler)
    app.add_exception_handler(TicketStateError, ticket_state_handler)
    app.add_exception_handler(WebhookNotFoundError, webhook_not_found_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)


async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Normalize explicit and framework-generated HTTP errors."""

    code = getattr(
        exc,
        "code",
        _DEFAULT_HTTP_ERROR_CODES.get(exc.status_code, "REQUEST_FAILED"),
    )
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return useful JSON-safe Pydantic errors in the common envelope."""

    details = [
        ValidationErrorDetail(
            field=".".join(str(part) for part in error.get("loc", ())),
            message=str(error.get("msg", "Invalid value")),
        )
        for error in exc.errors()
    ]
    return _error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
    )


async def invalid_refresh_token_handler(
    _request: Request,
    _exc: InvalidRefreshTokenError,
) -> JSONResponse:
    """Map invalid refresh-token exchanges without exposing token internals."""

    return _authentication_response(
        code="INVALID_REFRESH_TOKEN",
        message="Invalid refresh token",
    )


async def authentication_error_handler(
    _request: Request,
    _exc: AuthenticationError,
) -> JSONResponse:
    """Map failed logins to a deliberately generic public error."""

    return _authentication_response(
        code="INVALID_CREDENTIALS",
        message="Invalid email or password",
    )


async def duplicate_email_handler(
    _request: Request,
    _exc: DuplicateEmailError,
) -> JSONResponse:
    """Map duplicate customer registration to a conflict response."""

    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="EMAIL_ALREADY_REGISTERED",
        message="Email is already registered",
    )


async def ticket_not_found_handler(
    _request: Request,
    _exc: TicketNotFoundError,
) -> JSONResponse:
    """Hide the distinction between missing and inaccessible tickets."""

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="TICKET_NOT_FOUND",
        message="Ticket not found",
    )


async def ticket_state_handler(
    _request: Request,
    exc: TicketStateError,
) -> JSONResponse:
    """Map ticket workflow and mutability conflicts to HTTP 409."""

    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code=exc.code,
        message=str(exc),
    )


async def webhook_not_found_handler(
    _request: Request,
    _exc: WebhookNotFoundError,
) -> JSONResponse:
    """Map an unknown or inactive webhook registration."""

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="WEBHOOK_NOT_FOUND",
        message="Webhook registration not found",
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Log unexpected failures and return no internal implementation details."""

    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
    )


def _authentication_response(*, code: str, message: str) -> JSONResponse:
    """Return a bearer authentication failure with its required challenge header."""

    return _error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=code,
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ValidationErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build the one JSON representation used by every API error handler."""

    content = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details)
    ).model_dump(mode="json")
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=dict(headers) if headers is not None else None,
    )
