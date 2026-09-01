"""
tests/unit/test_webhook_security.py

Unit tests for Razorpay webhook signature verification (HMAC-SHA256).

Tests cover:
- Valid signature calculation and verification
- Invalid signatures
- Tampered request body
- Modified signature string
- Missing signature header
- Incorrect webhook secret
- Empty body & secret edge cases
"""

import pytest

from infrastructure.security.webhook_verifier import (
    compute_razorpay_signature,
    verify_razorpay_signature,
)


class TestSignatureVerification:
    def test_valid_signature(self):
        secret = "secret_key_123"
        body = b'{"event":"payment.captured","payload":{}}'
        signature = compute_razorpay_signature(body, secret)

        assert verify_razorpay_signature(body, signature, secret) is True

    def test_invalid_signature(self):
        secret = "secret_key_123"
        body = b'{"event":"payment.captured"}'
        bogus_signature = "invalid_signature_hex_value_00000000000000000000000000000000"

        assert verify_razorpay_signature(body, bogus_signature, secret) is False

    def test_tampered_body_rejected(self):
        """Modifying even 1 byte in the body invalidates the signature."""
        secret = "secret_key_123"
        original_body = b'{"amount": 1000}'
        tampered_body = b'{"amount": 1001}'
        signature = compute_razorpay_signature(original_body, secret)

        assert verify_razorpay_signature(tampered_body, signature, secret) is False

    def test_modified_signature_rejected(self):
        secret = "secret_key_123"
        body = b'{"amount": 1000}'
        signature = compute_razorpay_signature(body, secret)
        tampered_signature = signature[:-1] + ("0" if signature[-1] != "0" else "1")

        assert verify_razorpay_signature(body, tampered_signature, secret) is False

    def test_missing_signature(self):
        secret = "secret_key_123"
        body = b'{"event":"payment.failed"}'

        assert verify_razorpay_signature(body, None, secret) is False
        assert verify_razorpay_signature(body, "", secret) is False

    def test_wrong_secret_rejected(self):
        secret_a = "secret_alpha"
        secret_b = "secret_beta"
        body = b'{"event":"payment.authorized"}'
        signature = compute_razorpay_signature(body, secret_a)

        assert verify_razorpay_signature(body, signature, secret_b) is False

    def test_empty_secret_handling(self):
        body = b'{"event":"payment.captured"}'
        assert verify_razorpay_signature(body, "any_sig", "") is False
        assert verify_razorpay_signature(body, "any_sig", None) is False

    def test_whitespace_in_signature_handled(self):
        secret = "secret_key_123"
        body = b'{"event":"payment.captured"}'
        signature = compute_razorpay_signature(body, secret)

        assert verify_razorpay_signature(body, f"  {signature}  \n", secret) is True
