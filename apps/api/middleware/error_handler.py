"""
apps/api/middleware/error_handler.py

Structured exception handlers for FastAPI.

ARCHITECTURAL PRINCIPLES (Block 8, Requirement 1):
1. Returns standard structured JSON error payloads with error_code, message, correlation_id, timestamp.
2. NEVER exposes internal stack traces, DB credentials, raw SQL, API keys, or LLM reasoning.
3. Maps domain errors to appropriate HTTP status codes deterministically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.middleware.correlation import get_correlation_id
from domain.shared.errors import (
    DomainError,
    DuplicateRecoveryCaseError,
    InvalidActionError,
    InvalidMoneyAmountError,
    InvalidStateTransitionError,
    PaymentNotRecoverableError,
    PolicyViolationError,
    RecoveryCaseError,
)

logger = logging.getLogger("apps.api.error_handler")


def _format_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Any = None,
) -> JSONResponse:
    """Format structured, sanitized API error response."""
    payload: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "correlation_id": get_correlation_id(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    if details:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all structured exception handlers on the FastAPI application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error_code = "HTTP_ERROR"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            error_code = "RESOURCE_NOT_FOUND"
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            error_code = "UNAUTHORIZED"
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            error_code = "FORBIDDEN"
        elif exc.status_code == status.HTTP_400_BAD_REQUEST:
            error_code = "BAD_REQUEST"

        message = str(exc.detail) if isinstance(exc.detail, str) else "An HTTP error occurred."
        return _format_error_response(
            error_code=error_code,
            message=message,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Request validation failed for %s: %s", request.url.path, exc.errors())
        # Sanitize error messages to not leak internal structures
        simplified_errors = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            simplified_errors.append(f"{loc}: {err.get('msg', 'Invalid input')}")

        return _format_error_response(
            error_code="VALIDATION_ERROR",
            message="Request validation failed. Please verify input parameters.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=simplified_errors,
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def state_transition_exception_handler(
        request: Request, exc: InvalidStateTransitionError
    ) -> JSONResponse:
        return _format_error_response(
            error_code="INVALID_STATE_TRANSITION",
            message=str(exc),
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(PolicyViolationError)
    async def policy_violation_exception_handler(
        request: Request, exc: PolicyViolationError
    ) -> JSONResponse:
        return _format_error_response(
            error_code="POLICY_VIOLATION",
            message=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(DuplicateRecoveryCaseError)
    async def duplicate_case_exception_handler(
        request: Request, exc: DuplicateRecoveryCaseError
    ) -> JSONResponse:
        return _format_error_response(
            error_code="DUPLICATE_RESOURCE",
            message=str(exc),
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(RecoveryCaseError)
    async def recovery_case_exception_handler(
        request: Request, exc: RecoveryCaseError
    ) -> JSONResponse:
        return _format_error_response(
            error_code="RECOVERY_CASE_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _format_error_response(
            error_code="DOMAIN_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback internally for operations/debugging
        logger.error(
            "Unhandled exception during %s request to %s [correlation_id=%s]: %s",
            request.method,
            request.url.path,
            get_correlation_id(),
            str(exc),
            exc_info=True,
        )
        # Return sanitized message to user without stack trace or DB internals
        return _format_error_response(
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred. Please contact support.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
