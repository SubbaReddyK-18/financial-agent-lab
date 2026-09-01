"""
tests/unit/test_production_resilience.py

Unit tests for Block 8: Production Readiness, API Hardening & Operational Resilience.

Tests:
1. Structured error responses and exception sanitization
2. Correlation ID middleware and context propagation
3. Config-driven authentication/authorization boundaries
4. Health and readiness endpoints
5. Configuration validation and secret masking
6. Structured logging secret sanitization
7. Outbox worker lifecycle and graceful shutdown
"""

import json
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.exceptions import HTTPException

from apps.api.main import app, create_app
from apps.api.middleware.correlation import get_correlation_id, set_correlation_id
from apps.api.middleware.error_handler import _format_error_response
from apps.api.routes.health import health, health_db, readiness
from apps.api.security.auth import verify_admin_auth
from apps.api.settings import Settings, get_settings
from domain.shared.errors import (
    DomainError,
    DuplicateRecoveryCaseError,
    InvalidStateTransitionError,
    PolicyViolationError,
)
from infrastructure.logging import sanitize_log_message
from infrastructure.workers.outbox_worker import OutboxWorker

pytestmark = pytest.mark.unit


class TestStructuredErrorResponses:
    @pytest.mark.asyncio
    async def test_error_response_shape(self):
        resp = _format_error_response(
            error_code="TEST_ERROR",
            message="Something went wrong",
            status_code=400,
        )
        data = json.loads(resp.body.decode("utf-8"))
        assert resp.status_code == 400
        assert data["error_code"] == "TEST_ERROR"
        assert data["message"] == "Something went wrong"
        assert "correlation_id" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_validation_error_returns_structured_422(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Post malformed JSON / missing fields to /ai/decide
            res = await ac.post("/ai/decide", json={"amount_minor": -500})
            assert res.status_code == 422
            body = res.json()
            assert body["error_code"] == "VALIDATION_ERROR"
            assert "correlation_id" in body
            assert "timestamp" in body

    @pytest.mark.asyncio
    async def test_not_found_returns_structured_404(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get(f"/observability/simulation/{uuid.uuid4()}")
            assert res.status_code == 404
            body = res.json()
            assert body["error_code"] == "RESOURCE_NOT_FOUND" or body["error_code"] == "HTTP_ERROR"
            assert "correlation_id" in body


class TestCorrelationIdMiddleware:
    @pytest.mark.asyncio
    async def test_generates_correlation_id_when_missing(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/health")
            assert res.status_code == 200
            assert "X-Correlation-ID" in res.headers
            cid = res.headers["X-Correlation-ID"]
            assert len(cid) > 10

    @pytest.mark.asyncio
    async def test_echoes_incoming_correlation_id(self):
        custom_cid = "custom-trace-123456"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/health", headers={"X-Correlation-ID": custom_cid})
            assert res.status_code == 200
            assert res.headers.get("X-Correlation-ID") == custom_cid

    @pytest.mark.asyncio
    async def test_correlation_id_precedence_over_request_id(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get(
                "/health",
                headers={
                    "X-Correlation-ID": "primary-cid-100",
                    "X-Request-ID": "secondary-req-200",
                },
            )
            assert res.status_code == 200
            assert res.headers.get("X-Correlation-ID") == "primary-cid-100"

    @pytest.mark.asyncio
    async def test_oversized_or_invalid_correlation_id_sanitized(self):
        malicious_cid = "bad\r\nheader" + ("A" * 300)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/health", headers={"X-Correlation-ID": malicious_cid})
            assert res.status_code == 200
            # Should have generated a clean safe UUID rather than accepting malicious injection
            returned_cid = res.headers.get("X-Correlation-ID")
            assert len(returned_cid) < 100
            assert "bad" not in returned_cid

    def test_correlation_context_getter_setter(self):
        cid = set_correlation_id("test-corr-id")
        assert cid == "test-corr-id"
        assert get_correlation_id() == "test-corr-id"


class TestAuthenticationBoundary:
    @pytest.mark.asyncio
    async def test_admin_auth_passes_when_unconfigured(self):
        settings = Settings(admin_api_key=None)
        # Should not raise
        await verify_admin_auth(api_key=None, settings=settings)

    @pytest.mark.asyncio
    async def test_admin_auth_rejects_missing_key_when_configured(self):
        settings = Settings(admin_api_key="secret-key-123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_auth(api_key=None, settings=settings)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_auth_rejects_invalid_key(self):
        settings = Settings(admin_api_key="secret-key-123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_auth(api_key="wrong-key", settings=settings)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_auth_accepts_valid_key(self):
        settings = Settings(admin_api_key="secret-key-123")
        # Should not raise
        await verify_admin_auth(api_key="secret-key-123", settings=settings)


class TestHealthAndReadinessEndpoints:
    @pytest.mark.asyncio
    async def test_health_liveness(self):
        settings = Settings(app_env="test")
        res = await health(settings=settings)
        assert res["status"] == "ok"
        assert res["service"] == "financial-agent-lab"
        assert res["environment"] == "test"

    @pytest.mark.asyncio
    async def test_readiness_healthy_db(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result

        mock_resp = MagicMock()
        settings = Settings(app_env="test")

        res = await readiness(response=mock_resp, db=mock_session, settings=settings)
        assert res["status"] == "ready"
        assert res["database"] == "connected"

    @pytest.mark.asyncio
    async def test_readiness_failing_db_returns_503(self):
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB Connection Refused")

        mock_resp = MagicMock()
        settings = Settings(app_env="test")

        res = await readiness(response=mock_resp, db=mock_session, settings=settings)
        assert res["status"] == "unready"
        assert res["database"] == "unreachable"
        assert mock_resp.status_code == 503


class TestConfigurationHardening:
    def test_production_mode_requires_db_password(self):
        with pytest.raises(ValueError, match="DB_PASSWORD must be set in production"):
            Settings(
                app_env="production",
                db_password="",
                razorpay_webhook_secret="secure_secret_abc123",
            )

    def test_production_mode_requires_secure_webhook_secret(self):
        with pytest.raises(ValueError, match="secure RAZORPAY_WEBHOOK_SECRET must be set in production"):
            Settings(
                app_env="production",
                db_password="strong_password_123",
                razorpay_webhook_secret="test_webhook_secret_local",
            )

    def test_secrets_masked_in_sanitized_dict_and_repr(self):
        s = Settings(
            db_password="super_secret_db_pass",
            razorpay_webhook_secret="secret_wh_key",
            ai_api_key="ai_live_key_xyz",
            admin_api_key="admin_secret_999",
        )
        d = s.sanitized_dict()
        assert d["db_password"] == "***REDACTED***"
        assert d["razorpay_webhook_secret"] == "***REDACTED***"
        assert d["ai_api_key"] == "***REDACTED***"
        assert d["admin_api_key"] == "***REDACTED***"
        assert "super_secret_db_pass" not in repr(s)
        assert "secret_wh_key" not in repr(s)


class TestStructuredLogging:
    def test_sanitize_log_message_masks_secrets(self):
        raw = "Connecting with api_key='secret123' and password='my_password!'"
        sanitized = sanitize_log_message(raw)
        assert "secret123" not in sanitized
        assert "my_password!" not in sanitized
        assert "***REDACTED***" in sanitized

    def test_sanitize_log_message_masks_db_urls(self):
        raw = "Connected to postgresql+asyncpg://fal_user:super_secret_db_pass@localhost:5432/financial_agent_lab"
        sanitized = sanitize_log_message(raw)
        assert "super_secret_db_pass" not in sanitized
        assert "***REDACTED***" in sanitized

    def test_sanitize_log_message_masks_gemini_api_key(self):
        raw = "Sending request with AIzaSyD9ExampleKey12345678901234567 to Google API"
        sanitized = sanitize_log_message(raw)
        assert "AIzaSyD9ExampleKey12345678901234567" not in sanitized
        assert "***REDACTED_GEMINI_KEY***" in sanitized


class TestOutboxWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_worker_single_batch_execution(self):
        mock_control_plane = AsyncMock()
        mock_control_plane.process_outbox_batch.return_value = []

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        worker = OutboxWorker(
            session_factory=mock_factory,
            poll_interval_seconds=0.1,
            batch_limit=5,
            control_plane=mock_control_plane,
        )

        res = await worker.process_single_batch()
        assert res == []
        mock_control_plane.process_outbox_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_graceful_stop(self):
        mock_control_plane = AsyncMock()
        mock_control_plane.process_outbox_batch.return_value = []

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        worker = OutboxWorker(
            session_factory=mock_factory,
            poll_interval_seconds=0.05,
            batch_limit=5,
            control_plane=mock_control_plane,
        )

        # Stop worker immediately after starting
        worker.stop()
        await worker.run()
        assert worker._is_running is False
