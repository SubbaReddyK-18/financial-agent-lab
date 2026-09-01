"""
apps/api/middleware/correlation.py

Request correlation context middleware and utilities.
Manages correlation IDs across HTTP requests, background workers, and domain audit logs.
"""

from __future__ import annotations

import contextvars
import re
import uuid
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SAFE_CID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")

# Context variable holding the active request correlation ID
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Retrieve the active correlation ID or generate a new one if not set."""
    cid = correlation_id_ctx.get()
    if not cid:
        cid = str(uuid.uuid4())
        correlation_id_ctx.set(cid)
    return cid


def set_correlation_id(cid: Optional[str] = None) -> str:
    """
    Explicitly set or generate the active correlation ID in the context.
    Validates against oversized / malicious characters before accepting.
    """
    if cid:
        cleaned = cid.strip()
        if SAFE_CID_PATTERN.match(cleaned):
            correlation_id_ctx.set(cleaned)
            return cleaned

    final_cid = str(uuid.uuid4())
    correlation_id_ctx.set(final_cid)
    return final_cid


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette middleware that extracts or generates a correlation ID,
    binds it to the context, and attaches it to the response headers.

    Precedence:
    1. X-Correlation-ID header (if valid safe string <= 128 chars)
    2. X-Request-ID header (if valid safe string <= 128 chars)
    3. Auto-generated UUID4.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        header_cid = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
        )
        cid = set_correlation_id(header_cid)

        # Process the request
        response = await call_next(request)

        # Attach correlation ID to response headers
        response.headers["X-Correlation-ID"] = cid
        return response
