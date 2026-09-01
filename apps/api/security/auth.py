"""
apps/api/security/auth.py

Configuration-driven authentication and authorization boundaries.

ARCHITECTURAL PRINCIPLES (Block 8, Requirement 4):
1. Protects administrative and decision triggering endpoints with an optional API key / Bearer token.
2. Uses constant-time string comparison (secrets.compare_digest) to prevent timing attacks.
3. Observability and health endpoints remain strictly read-only and non-mutating.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from apps.api.settings import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_admin_auth(
    api_key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Validate administrative access token if ADMIN_API_KEY is configured in settings.
    If ADMIN_API_KEY is unset (e.g. in default local development), access is permitted.
    When configured, requires constant-time matching X-API-Key header.
    """
    admin_key = settings.admin_api_key
    if not admin_key:
        # Development / unrestricted mode
        return

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required API key header 'X-API-Key'.",
        )

    # Constant-time comparison
    if not secrets.compare_digest(api_key.encode("utf-8"), admin_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or unauthorized API key.",
        )


async def require_configured_admin_auth(
    api_key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Authenticate an actor for the recovery-action approval boundary."""
    admin_key = settings.admin_api_key
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recovery approval is unavailable until ADMIN_API_KEY is configured.",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required API key header 'X-API-Key'.",
        )
    if not secrets.compare_digest(api_key.encode("utf-8"), admin_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or unauthorized API key.",
        )
    # Keep a durable, attributable principal without persisting the credential.
    return "admin_api_key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
