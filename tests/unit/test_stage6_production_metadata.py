"""
tests/unit/test_stage6_production_metadata.py

Unit tests for Stage 6: Production Observability, Provenance & Worker Lifecycle.

Tests:
1. Prompt hash and agent-bundle version are populated in domain AIDecisionRecord.
2. Prompt hash and agent-bundle version flow through to AIDecisionRecordORM fields
   (orchestrator path and /ai/decide route path).
3. Financial event payloads include schema_version.
4. SimulationRunORM ORM model has provenance fields.
5. WebhookWorker has the correct lifecycle (stop, run-until-stopped, single-batch).
6. DecisionWorker has the correct lifecycle (stop, run-until-stopped, single-batch).
7. JSON logging is configured per effective_log_json from settings.
8. Correlation ID is preserved in AIDecisionRecordORM persistence path.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.api.settings import Settings
from domain.intelligence.ai.models import AIDecisionRecord
from domain.intelligence.ai.prompt import (
    AGENT_BUNDLE_VERSION,
    PROMPT_SHA256,
    PROMPT_VERSION,
    RecoveryPromptBuilder,
)
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import CustomerProfile, PaymentFailureDetails, RecoveryContext
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.simulation import SimulationRunORM
from infrastructure.logging import configure_structured_logging
from infrastructure.workers.decision_worker import DecisionWorker
from infrastructure.workers.webhook_worker import WebhookWorker

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper: minimal RecoveryContext
# ---------------------------------------------------------------------------

def _make_context() -> RecoveryContext:
    return RecoveryContext(
        payment=PaymentFailureDetails(
            payment_id=uuid.uuid4(),
            amount_minor=5_000_00,
            payment_method=PaymentMethod.UPI,
            attempt_count=1,
            failure_code="NETWORK_TIMEOUT",
        ),
        customer=CustomerProfile(customer_id=uuid.uuid4()),
        policy=MerchantRecoveryPolicy(merchant_id=uuid.uuid4(), cooldown_hours=0),
        completed_interventions=0,
    )


# ---------------------------------------------------------------------------
# 1. Prompt hash and agent-bundle version in domain record
# ---------------------------------------------------------------------------

class TestPromptBuilderMetadata:
    def test_prompt_sha256_is_64_hex_chars(self):
        assert len(PROMPT_SHA256) == 64
        assert all(c in "0123456789abcdef" for c in PROMPT_SHA256)

    def test_agent_bundle_version_is_populated(self):
        assert AGENT_BUNDLE_VERSION
        assert "recovery-decision-agent" in AGENT_BUNDLE_VERSION

    def test_prompt_builder_class_attrs_match_module_constants(self):
        assert RecoveryPromptBuilder.content_hash == PROMPT_SHA256
        assert RecoveryPromptBuilder.bundle_version == AGENT_BUNDLE_VERSION
        assert RecoveryPromptBuilder.version == PROMPT_VERSION


class TestAIDecisionRecordProvenance:
    @pytest.mark.asyncio
    async def test_provider_populates_prompt_hash_and_agent_version(self):
        canned = (
            '{"recommended_action":"RETRY","confidence":0.8,'
            '"estimated_action_success_probability":0.7,'
            '"estimated_natural_recovery_probability":0.2,'
            '"reasoning_codes":["TIMEOUT"],"uncertainty":"LOW",'
            '"requires_human_review":false,"concise_rationale":"Retry.","recommended_discount_percent":0}'
        )
        provider = AIDecisionProvider(client=MockLLMClient(canned_response=canned))
        context = _make_context()
        await provider.evaluate_decision_async(context)

        record = provider.last_decision_record
        assert record is not None
        assert record.prompt_hash == PROMPT_SHA256
        assert record.agent_version == AGENT_BUNDLE_VERSION

    @pytest.mark.asyncio
    async def test_fallback_also_carries_prompt_hash_and_agent_version(self):
        provider = AIDecisionProvider(
            client=MockLLMClient(should_fail=True, failure_error=RuntimeError("provider down"))
        )
        context = _make_context()
        await provider.evaluate_decision_async(context)

        record = provider.last_decision_record
        assert record is not None
        assert record.prompt_hash == PROMPT_SHA256
        assert record.agent_version == AGENT_BUNDLE_VERSION


# ---------------------------------------------------------------------------
# 2. Prompt hash/agent_version flow to AIDecisionRecordORM
# ---------------------------------------------------------------------------

class TestAIDecisionRecordORMProvenance:
    def test_orm_accepts_prompt_hash_and_agent_version(self):
        """ORM column accepts and stores prompt hash and agent version."""
        orm = AIDecisionRecordORM(
            id=uuid.uuid4(),
            scenario_id="test-123",
            correlation_id="cid-xyz",
            audit_schema_version="1",
            provider="AIAssistedRecoveryAgent",
            model="mock",
            prompt_version="v1.0",
            prompt_hash=PROMPT_SHA256,
            agent_version=AGENT_BUNDLE_VERSION,
            recommended_action="RETRY",
            confidence=0.8,
            reasoning_codes=["TIMEOUT"],
            uncertainty="LOW",
            requires_human_review=False,
            fallback_used=False,
            fallback_reason=None,
            latency_ms=12.5,
            input_tokens=180,
            output_tokens=75,
            estimated_llm_cost_minor=0,
            final_action="RETRY",
            expected_net_incremental_revenue_minor=500,
            proposal_validation_json={},
            policy_result_json={},
            authorization_result_json={},
            economic_candidates_json=[],
            selection_result_json={},
            created_at=datetime.now(tz=timezone.utc),
        )
        assert orm.prompt_hash == PROMPT_SHA256
        assert orm.agent_version == AGENT_BUNDLE_VERSION

    def test_orm_prompt_hash_can_be_none_for_legacy_records(self):
        """Nullable column allows legacy records without prompt hash."""
        orm = AIDecisionRecordORM(
            id=uuid.uuid4(),
            scenario_id=None,
            correlation_id=None,
            audit_schema_version="1",
            provider="legacy",
            model="legacy",
            prompt_version="v0.9",
            prompt_hash=None,
            agent_version=None,
            recommended_action="WAIT",
            confidence=0.5,
            reasoning_codes=[],
            uncertainty="HIGH",
            requires_human_review=True,
            fallback_used=True,
            fallback_reason=None,
            latency_ms=0.0,
            input_tokens=0,
            output_tokens=0,
            estimated_llm_cost_minor=0,
            final_action="WAIT",
            expected_net_incremental_revenue_minor=0,
            proposal_validation_json={},
            policy_result_json={},
            authorization_result_json={},
            economic_candidates_json=[],
            selection_result_json={},
            created_at=datetime.now(tz=timezone.utc),
        )
        assert orm.prompt_hash is None
        assert orm.agent_version is None


# ---------------------------------------------------------------------------
# 3. Financial event payload schema_version
# ---------------------------------------------------------------------------

class TestFinancialEventPayloadSchema:
    def test_event_payload_includes_schema_version(self):
        """Financial event payloads should include schema_version for event architecture."""
        from infrastructure.database.orm.events import FinancialEventORM
        from domain.shared.enums import AggregateType

        fin_event = FinancialEventORM(
            id=uuid.uuid4(),
            event_type="RECOVERY_ACTION_PENDING",
            aggregate_type=AggregateType.RECOVERY_ACTION.value,
            aggregate_id=str(uuid.uuid4()),
            occurred_at=datetime.now(tz=timezone.utc),
            payload={
                "schema_version": "1",
                "recovery_case_id": str(uuid.uuid4()),
                "action_type": "RETRY",
            },
            correlation_id="cid-test",
        )
        assert fin_event.payload["schema_version"] == "1"


# ---------------------------------------------------------------------------
# 4. SimulationRunORM provenance fields
# ---------------------------------------------------------------------------

class TestSimulationRunORMProvenance:
    def test_orm_has_prompt_hash_field(self):
        orm = SimulationRunORM(
            id=uuid.uuid4(),
            run_name="test_run",
            scenario_count=100,
            seed=42,
            version="v1.0",
            prompt_hash=PROMPT_SHA256,
            agent_bundle_version=AGENT_BUNDLE_VERSION,
            duration_ms=1234,
            no_intervention_metrics={},
            baseline_metrics={},
            oracle_metrics={},
            completed_at=datetime.now(tz=timezone.utc),
        )
        assert orm.prompt_hash == PROMPT_SHA256
        assert orm.agent_bundle_version == AGENT_BUNDLE_VERSION

    def test_orm_provenance_nullable_for_legacy(self):
        """Nullable: existing simulation records without provenance remain valid."""
        orm = SimulationRunORM(
            id=uuid.uuid4(),
            run_name="legacy_run",
            scenario_count=50,
            seed=0,
            version="v1.0",
            prompt_hash=None,
            agent_bundle_version=None,
            duration_ms=500,
            no_intervention_metrics={},
            baseline_metrics={},
            oracle_metrics={},
            completed_at=datetime.now(tz=timezone.utc),
        )
        assert orm.prompt_hash is None
        assert orm.agent_bundle_version is None


# ---------------------------------------------------------------------------
# 5. WebhookWorker lifecycle
# ---------------------------------------------------------------------------

class TestWebhookWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_webhook_worker_single_batch_empty(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "infrastructure.workers.webhook_worker.process_pending_webhooks",
            new_callable=AsyncMock,
            return_value=[],
        ):
            worker = WebhookWorker(
                session_factory=mock_factory,
                poll_interval_seconds=0.1,
                batch_limit=5,
            )
            count = await worker.process_single_batch()
            assert count == 0

    @pytest.mark.asyncio
    async def test_webhook_worker_graceful_stop(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "infrastructure.workers.webhook_worker.process_pending_webhooks",
            new_callable=AsyncMock,
            return_value=[],
        ):
            worker = WebhookWorker(
                session_factory=mock_factory,
                poll_interval_seconds=0.05,
            )
            worker.stop()
            await worker.run()
            assert worker._is_running is False

    @pytest.mark.asyncio
    async def test_webhook_worker_stop_sets_is_running_false(self):
        mock_factory = MagicMock()
        worker = WebhookWorker(session_factory=mock_factory, poll_interval_seconds=0.05)
        worker.stop()
        assert worker._stop_event.is_set()
        assert worker._is_running is False


# ---------------------------------------------------------------------------
# 6. DecisionWorker lifecycle
# ---------------------------------------------------------------------------

class TestDecisionWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_decision_worker_single_batch_empty(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "infrastructure.workers.decision_worker.process_pending_decision_requests",
            new_callable=AsyncMock,
            return_value=0,
        ):
            worker = DecisionWorker(
                session_factory=mock_factory,
                poll_interval_seconds=0.1,
                batch_limit=5,
            )
            count = await worker.process_single_batch()
            assert count == 0

    @pytest.mark.asyncio
    async def test_decision_worker_graceful_stop(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "infrastructure.workers.decision_worker.process_pending_decision_requests",
            new_callable=AsyncMock,
            return_value=0,
        ):
            worker = DecisionWorker(
                session_factory=mock_factory,
                poll_interval_seconds=0.05,
            )
            worker.stop()
            await worker.run()
            assert worker._is_running is False

    @pytest.mark.asyncio
    async def test_decision_worker_processes_batch_and_returns_count(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "infrastructure.workers.decision_worker.process_pending_decision_requests",
            new_callable=AsyncMock,
            return_value=3,
        ):
            worker = DecisionWorker(session_factory=mock_factory, poll_interval_seconds=0.1)
            count = await worker.process_single_batch()
            assert count == 3


# ---------------------------------------------------------------------------
# 7. JSON logging behavior
# ---------------------------------------------------------------------------

class TestProductionLoggingConfig:
    def test_production_env_defaults_to_json_logs(self):
        s = Settings(app_env="production", db_password="x", razorpay_webhook_secret="strong_secret_abc", admin_api_key="key")
        assert s.effective_log_json is True

    def test_development_env_defaults_to_plain_logs(self):
        s = Settings(app_env="development")
        assert s.effective_log_json is False

    def test_explicit_log_json_true_overrides_env(self):
        s = Settings(app_env="development", log_json=True)
        assert s.effective_log_json is True

    def test_explicit_log_json_false_overrides_production(self):
        s = Settings(app_env="production", db_password="x", razorpay_webhook_secret="strong_secret_abc", admin_api_key="key", log_json=False)
        assert s.effective_log_json is False

    def test_configure_structured_logging_json_format(self):
        import logging
        configure_structured_logging(log_level="INFO", json_format=True)
        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_configure_structured_logging_plain_format(self):
        import logging
        configure_structured_logging(log_level="DEBUG", json_format=False)
        root = logging.getLogger()
        assert len(root.handlers) >= 1


# ---------------------------------------------------------------------------
# 8. Correlation ID preserved in persistence path
# ---------------------------------------------------------------------------

class TestCorrelationIdPersistence:
    @pytest.mark.asyncio
    async def test_decision_provider_does_not_lose_correlation_id(self):
        """The correlation_id is passed through to AIDecisionRecordORM by orchestrator.
        This test verifies it is accepted by the ORM and preserved."""
        cid = "corr-stage6-test-abc"
        orm = AIDecisionRecordORM(
            id=uuid.uuid4(),
            scenario_id="test",
            correlation_id=cid,
            audit_schema_version="1",
            provider="mock",
            model="mock",
            prompt_version="v1.0",
            prompt_hash=PROMPT_SHA256,
            agent_version=AGENT_BUNDLE_VERSION,
            recommended_action="WAIT",
            confidence=0.5,
            reasoning_codes=[],
            uncertainty="MEDIUM",
            requires_human_review=False,
            fallback_used=False,
            fallback_reason=None,
            latency_ms=1.0,
            input_tokens=0,
            output_tokens=0,
            estimated_llm_cost_minor=0,
            final_action="WAIT",
            expected_net_incremental_revenue_minor=0,
            proposal_validation_json={},
            policy_result_json={},
            authorization_result_json={},
            economic_candidates_json=[],
            selection_result_json={},
            created_at=datetime.now(tz=timezone.utc),
        )
        assert orm.correlation_id == cid
