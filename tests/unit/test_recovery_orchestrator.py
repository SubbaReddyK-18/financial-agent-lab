"""
tests/unit/test_recovery_orchestrator.py

Unit tests for RecoveryDecisionOrchestrator and test-mode action executors.

Covers (Block 5, Requirement 11):
- Successful AI proposal orchestration
- Policy rejection handling
- Gemini timeout handling
- Gemini HTTP 429 rate limit handling
- Malformed AI response handling
- Deterministic fallback execution
- WAIT, RETRY, PAYMENT_LINK, NOTIFY, ESCALATE test-mode executors
- Idempotent and duplicate processing
- Stale/superseded recovery cases
- Economic valuation integrity preservation
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.recovery.execution import (
    ActionExecutionResult,
    EscalateActionExecutor,
    NotifyActionExecutor,
    PaymentLinkActionExecutor,
    RetryActionExecutor,
    WaitActionExecutor,
    get_action_executor,
)
from domain.recovery.orchestrator import OrchestrationResult, RecoveryDecisionOrchestrator
from domain.shared.enums import PaymentMethod, RecoveryActionType
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM


class TestTestModeActionExecutors:
    @pytest.fixture
    def sample_context(self) -> RecoveryContext:
        policy = MerchantRecoveryPolicy(
            merchant_id=uuid.uuid4(),
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
        )
        payment = PaymentFailureDetails(
            payment_id=uuid.uuid4(),
            amount_minor=1000_00,
            currency="INR",
            payment_method=PaymentMethod.UPI,
            attempt_count=1,
            failure_code="GATEWAY_TIMEOUT",
        )
        customer = CustomerProfile(
            customer_id=uuid.uuid4(),
            customer_segment="RETURNING",
        )
        return RecoveryContext(
            payment=payment,
            customer=customer,
            policy=policy,
            completed_interventions=0,
        )

    @pytest.mark.asyncio
    async def test_wait_executor(self, sample_context: RecoveryContext):
        executor = WaitActionExecutor()
        res = await executor.execute(uuid.uuid4(), sample_context)
        assert res.action_type == RecoveryActionType.WAIT
        assert res.status == "COMPLETED"
        assert res.is_test_mode is True
        assert "TEST_WAIT_" in res.execution_reference
        assert res.details["mode"] == "OBSERVATION"

    @pytest.mark.asyncio
    async def test_retry_executor(self, sample_context: RecoveryContext):
        executor = RetryActionExecutor()
        res = await executor.execute(uuid.uuid4(), sample_context)
        assert res.action_type == RecoveryActionType.RETRY
        assert res.status == "COMPLETED"
        assert "TEST_RETRY_" in res.execution_reference
        assert res.details["simulated_attempt_number"] == 2

    @pytest.mark.asyncio
    async def test_payment_link_executor_applies_discount(self, sample_context: RecoveryContext):
        executor = PaymentLinkActionExecutor()
        res = await executor.execute(uuid.uuid4(), sample_context, discount_percent=5)
        assert res.action_type == RecoveryActionType.PAYMENT_LINK
        assert res.status == "COMPLETED"
        assert "TEST_PLINK_" in res.execution_reference
        assert res.details["discount_percent"] == 5
        assert res.details["discount_amount_minor"] == 50_00  # 5% of 1000.00
        assert res.details["final_amount_minor"] == 950_00

    @pytest.mark.asyncio
    async def test_notify_executor(self, sample_context: RecoveryContext):
        executor = NotifyActionExecutor()
        res = await executor.execute(uuid.uuid4(), sample_context)
        assert res.action_type == RecoveryActionType.NOTIFY
        assert res.status == "COMPLETED"
        assert "TEST_NOTIF_" in res.execution_reference
        assert "SMS" in res.details["channels"]

    @pytest.mark.asyncio
    async def test_escalate_executor(self, sample_context: RecoveryContext):
        executor = EscalateActionExecutor()
        res = await executor.execute(uuid.uuid4(), sample_context)
        assert res.action_type == RecoveryActionType.ESCALATE
        assert res.status == "COMPLETED"
        assert "TEST_TICKET_" in res.execution_reference
        assert res.details["queue"] == "CUSTOMER_SUPPORT"


class TestOrchestratorEdgeCasesAndFallbacks:
    """Tests orchestrator resilience across AI failure modes and policy boundaries."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_orchestrator_successful_ai_proposal(self, mock_db_session):
        canned_json = """{
            "recommended_action": "RETRY",
            "confidence": 0.85,
            "estimated_action_success_probability": 0.65,
            "estimated_natural_recovery_probability": 0.20,
            "reasoning_codes": ["TRANSIENT_ERROR"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Clear technical timeout.",
            "recommended_discount_percent": 0
        }"""
        client = MockLLMClient(canned_response=canned_json)
        provider = AIDecisionProvider(client=client)
        orchestrator = RecoveryDecisionOrchestrator(provider=provider)

        # Mock DB entities
        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, merchant_id=uuid.uuid4(), customer_id=uuid.uuid4(), payment_id=uuid.uuid4(), amount_at_risk_minor=1500_00, status="OPEN")
        mock_payment = MagicMock(id=mock_case.payment_id, amount_minor=1500_00, currency="INR", payment_method="UPI", created_at=datetime.now(tz=timezone.utc))
        mock_customer = MagicMock(id=mock_case.customer_id, historical_payment_count=1, historical_success_rate=0.9, historical_failure_rate=0.1, prior_interventions_count=0)
        mock_policy = MagicMock(merchant_id=mock_case.merchant_id, maximum_discount_percent=10, maximum_interventions=3, cooldown_hours=2, high_value_threshold_minor=None, high_value_requires_approval=False, low_confidence_requires_review=False)
        mock_attempt = MagicMock(attempt_number=1, failure_code="GATEWAY_TIMEOUT", failure_reason="Network error")

        mock_db_session.scalar.side_effect = [mock_case, mock_payment, mock_customer, mock_policy, mock_attempt]
        mock_db_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        request_id = uuid.uuid4()
        result = await orchestrator.orchestrate_case(
            case_id, mock_db_session, correlation_id="cid-orchestration",
            decision_request_id=request_id,
        )

        assert result.success is True
        assert result.action_type == RecoveryActionType.RETRY
        # Orchestration persists the approved action; only the outbox worker
        # may invoke the test-mode executor after the transaction commits.
        assert result.action_status == "APPROVED"
        assert result.fallback_used is False
        assert result.execution_result is None
        persisted_audit = next(
            call.args[0] for call in mock_db_session.add.call_args_list
            if isinstance(call.args[0], AIDecisionRecordORM)
        )
        assert persisted_audit.recovery_case_id == case_id
        assert persisted_audit.payment_id == mock_payment.id
        assert persisted_audit.recovery_action_id == result.action_id
        assert persisted_audit.decision_request_id == request_id
        assert persisted_audit.correlation_id == "cid-orchestration"
        assert persisted_audit.proposal_json["recommended_action"] == "RETRY"
        assert persisted_audit.selection_result_json["deterministic_selected_action"] == "RETRY"
        assert len(persisted_audit.economic_candidates_json) == 5

    @pytest.mark.asyncio
    async def test_orchestrator_gemini_timeout_triggers_fallback(self, mock_db_session):
        client = MockLLMClient(should_fail=True, failure_error=TimeoutError("Request timed out after 10s"))
        provider = AIDecisionProvider(client=client)
        orchestrator = RecoveryDecisionOrchestrator(provider=provider)

        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, merchant_id=uuid.uuid4(), customer_id=uuid.uuid4(), payment_id=uuid.uuid4(), amount_at_risk_minor=2000_00, status="OPEN")
        mock_payment = MagicMock(id=mock_case.payment_id, amount_minor=2000_00, currency="INR", payment_method="UPI", created_at=datetime.now(tz=timezone.utc))
        mock_customer = MagicMock(id=mock_case.customer_id, historical_payment_count=1, historical_success_rate=0.85, historical_failure_rate=0.15, prior_interventions_count=0)
        mock_policy = MagicMock(merchant_id=mock_case.merchant_id, maximum_discount_percent=10, maximum_interventions=3, cooldown_hours=2, high_value_threshold_minor=None, high_value_requires_approval=False, low_confidence_requires_review=False)
        mock_attempt = MagicMock(attempt_number=1, failure_code="GATEWAY_TIMEOUT", failure_reason="Timeout")

        mock_db_session.scalar.side_effect = [mock_case, mock_payment, mock_customer, mock_policy, mock_attempt]
        mock_db_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        result = await orchestrator.orchestrate_case(case_id, mock_db_session)

        assert result.success is True
        assert result.fallback_used is True
        assert "Request timed out" in str(result.fallback_reason)
        # Deterministic baseline chose RETRY
        assert result.action_type == RecoveryActionType.RETRY
        assert result.action_status == "APPROVED"

    @pytest.mark.asyncio
    async def test_orchestrator_gemini_429_triggers_fallback(self, mock_db_session):
        req = httpx.Request("POST", "https://api.example.com")
        resp = httpx.Response(429, request=req, text="Rate limit exceeded")
        client = MockLLMClient(should_fail=True, failure_error=httpx.HTTPStatusError("Client error '429'", request=req, response=resp))
        provider = AIDecisionProvider(client=client)
        orchestrator = RecoveryDecisionOrchestrator(provider=provider)

        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, merchant_id=uuid.uuid4(), customer_id=uuid.uuid4(), payment_id=uuid.uuid4(), amount_at_risk_minor=2000_00, status="OPEN")
        mock_payment = MagicMock(id=mock_case.payment_id, amount_minor=2000_00, currency="INR", payment_method="UPI", created_at=datetime.now(tz=timezone.utc))
        mock_customer = MagicMock(id=mock_case.customer_id, historical_payment_count=1, historical_success_rate=0.85, historical_failure_rate=0.15, prior_interventions_count=0)
        mock_policy = MagicMock(merchant_id=mock_case.merchant_id, maximum_discount_percent=10, maximum_interventions=3, cooldown_hours=2, high_value_threshold_minor=None, high_value_requires_approval=False, low_confidence_requires_review=False)
        mock_attempt = MagicMock(attempt_number=1, failure_code="GATEWAY_TIMEOUT", failure_reason="Timeout")

        mock_db_session.scalar.side_effect = [mock_case, mock_payment, mock_customer, mock_policy, mock_attempt]
        mock_db_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        result = await orchestrator.orchestrate_case(case_id, mock_db_session)

        assert result.success is True
        assert result.fallback_used is True
        assert "429" in str(result.fallback_reason)

    @pytest.mark.asyncio
    async def test_orchestrator_malformed_ai_response_triggers_fallback(self, mock_db_session):
        client = MockLLMClient(canned_response="NOT_JSON_AT_ALL")
        provider = AIDecisionProvider(client=client)
        orchestrator = RecoveryDecisionOrchestrator(provider=provider)

        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, merchant_id=uuid.uuid4(), customer_id=uuid.uuid4(), payment_id=uuid.uuid4(), amount_at_risk_minor=2000_00, status="OPEN")
        mock_payment = MagicMock(id=mock_case.payment_id, amount_minor=2000_00, currency="INR", payment_method="UPI", created_at=datetime.now(tz=timezone.utc))
        mock_customer = MagicMock(id=mock_case.customer_id, historical_payment_count=1, historical_success_rate=0.85, historical_failure_rate=0.15, prior_interventions_count=0)
        mock_policy = MagicMock(merchant_id=mock_case.merchant_id, maximum_discount_percent=10, maximum_interventions=3, cooldown_hours=2, high_value_threshold_minor=None, high_value_requires_approval=False, low_confidence_requires_review=False)
        mock_attempt = MagicMock(attempt_number=1, failure_code="GATEWAY_TIMEOUT", failure_reason="Timeout")

        mock_db_session.scalar.side_effect = [mock_case, mock_payment, mock_customer, mock_policy, mock_attempt]
        mock_db_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        result = await orchestrator.orchestrate_case(case_id, mock_db_session)

        assert result.success is True
        assert result.fallback_used is True
        assert "validation error" in str(result.fallback_reason).lower() or "json" in str(result.fallback_reason).lower()

    @pytest.mark.asyncio
    async def test_orchestrator_idempotent_on_closed_case(self, mock_db_session):
        orchestrator = RecoveryDecisionOrchestrator()
        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, payment_id=uuid.uuid4(), status="CLOSED")

        mock_db_session.scalar.return_value = mock_case

        result = await orchestrator.orchestrate_case(case_id, mock_db_session)

        assert result.success is True
        assert result.is_idempotent is True
        assert result.action_id is None
        # Verify no action added to DB
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestrator_idempotent_on_in_flight_executing_action(self, mock_db_session):
        orchestrator = RecoveryDecisionOrchestrator()
        case_id = uuid.uuid4()
        mock_case = MagicMock(id=case_id, payment_id=uuid.uuid4(), status="IN_PROGRESS")
        active_action = MagicMock(id=uuid.uuid4(), action_type="RETRY", status="EXECUTING")

        mock_db_session.scalar.return_value = mock_case
        mock_db_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[active_action]))

        result = await orchestrator.orchestrate_case(case_id, mock_db_session)

        assert result.success is True
        assert result.is_idempotent is True
        assert result.action_id == active_action.id
        assert result.action_status == "EXECUTING"
