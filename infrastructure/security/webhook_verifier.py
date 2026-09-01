"""
infrastructure/security/webhook_verifier.py

Razorpay webhook signature verification component.

ARCHITECTURAL PRINCIPLES (P-01, P-02, Step 2):
- Signature must be calculated against the ORIGINAL RAW REQUEST BODY bytes.
- Never parse JSON or alter formatting before signature calculation.
- Constant-time string comparison (hmac.compare_digest) to prevent timing attacks.
- Never log webhook secrets, authorization headers, or sensitive signature material.
"""

from __future__ import annotations

import hashlib
import hmac


def compute_razorpay_signature(raw_body: bytes, secret: str) -> str:
    """
    Compute the HMAC-SHA256 hex digest for a raw request payload.

    Args:
        raw_body: Unmodified raw request body bytes.
        secret: The configured Razorpay webhook secret.

    Returns:
        Hex-encoded SHA-256 HMAC string.
    """
    if not secret:
        raise ValueError("Webhook secret cannot be empty.")
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_razorpay_signature(
    raw_body: bytes,
    signature: str | None,
    secret: str | None,
) -> bool:
    """
    Verify the authenticity of an incoming Razorpay webhook request.

    Args:
        raw_body: Original unmodified request body as raw bytes.
        signature: The value from the X-Razorpay-Signature HTTP header.
        secret: The configured webhook secret.

    Returns:
        True if signature is authentic, False otherwise.
    """
    if not signature or not secret:
        return False

    if not isinstance(raw_body, bytes):
        return False

    try:
        expected_signature = compute_razorpay_signature(raw_body, secret)
        # Constant-time comparison to prevent timing side-channel attacks
        return hmac.compare_digest(expected_signature, signature.strip())
    except Exception:
        return False
