"""Block 9 durable decision audit snapshot and reconstruction tests."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.intelligence.ai.audit_snapshot import build_decision_audit_snapshots
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import CustomerProfile, PaymentFailureDetails, RecoveryContext
from domain.observability.service import ObservabilityService
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM


def _provider_and_record():
    context = RecoveryContext(
        payment=PaymentFailureDetails(payment_id=uuid.uuid4(), amount_minor=50_000,
                                      payment_method=PaymentMethod.UPI, attempt_count=1,
                                      failure_code="TIMEOUT"),
        customer=CustomerProfile(customer_id=uuid.uuid4()),
        policy=MerchantRecoveryPolicy(merchant_id=uuid.uuid4(), cooldown_hours=0),
    )
    proposal = '{"recommended_action":"RETRY","confidence":0.8,"estimated_action_success_probability":0.7,"estimated_natural_recovery_probability":0.2,"reasoning_codes":["TIMEOUT"],"uncertainty":"LOW","requires_human_review":false,"concise_rationale":"Retry after timeout.","recommended_discount_percent":0}'
    provider = AIDecisionProvider(client=MockLLMClient(canned_response=proposal))
    return provider, context


@pytest.mark.asyncio
async def test_snapshot_preserves_ai_proposal_separately_from_deterministic_selection():
    provider, context = _provider_and_record()
    recommendation = await provider.evaluate_decision_async(context)
    snapshots = build_decision_audit_snapshots(provider.last_decision_record, recommendation)

    assert snapshots["proposal_json"]["recommended_action"] == "RETRY"
    assert snapshots["selection_result_json"]["deterministic_selected_action"] == recommendation.recommended_action.value
    assert snapshots["policy_result_json"]["policy_permitted_action"] == recommendation.policy_permitted_action.value
    assert len(snapshots["economic_candidates_json"]) == 5
    assert all(isinstance(x["expected_net_incremental_revenue_minor"], int) for x in snapshots["economic_candidates_json"])
    assert "chain_of_thought" not in snapshots["proposal_json"]
    assert "api_key" not in str(snapshots)


@pytest.mark.asyncio
async def test_fallback_snapshot_records_sanitized_validation_outcome():
    provider, context = _provider_and_record()
    provider._client = MockLLMClient(should_fail=True, failure_error=TimeoutError("provider token=secret-value unavailable"))
    recommendation = await provider.evaluate_decision_async(context)
    snapshots = build_decision_audit_snapshots(provider.last_decision_record, recommendation)

    assert snapshots["proposal_json"] is None
    assert snapshots["proposal_validation_json"]["fallback_triggered"] is True
    assert "secret-value" not in snapshots["proposal_validation_json"]["fallback_reason"]
    assert snapshots["selection_result_json"]["selection_source"] == "DETERMINISTIC_BASELINE_FALLBACK"


@pytest.mark.asyncio
async def test_observability_reconstructs_snapshot_approval_outbox_and_payment_links():
    decision_id, case_id, payment_id, action_id, request_id, event_id, outbox_id, approval_id = [uuid.uuid4() for _ in range(8)]
    audit = AIDecisionRecordORM(
        id=decision_id, scenario_id=str(case_id), recovery_case_id=case_id, payment_id=payment_id,
        decision_request_id=request_id, recovery_action_id=action_id, financial_event_id=event_id,
        correlation_id="cid-audit", audit_schema_version="1", provider="mock", model="mock",
        prompt_version="v1", recommended_action="PAYMENT_LINK", confidence=0.8,
        reasoning_codes=["TEST"], uncertainty="LOW", requires_human_review=False,
        fallback_used=False, fallback_reason=None, latency_ms=1.0, input_tokens=1, output_tokens=1,
        estimated_llm_cost_minor=0, final_action="RETRY", expected_net_incremental_revenue_minor=123,
        proposal_json={"recommended_action": "PAYMENT_LINK", "concise_rationale": "safe"},
        proposal_validation_json={"structurally_valid": True, "accepted": True},
        policy_result_json={"proposed_action_permitted": True},
        authorization_result_json={"approval_required": True, "decision_time_status": "PENDING_APPROVAL"},
        economic_candidates_json=[{"action_type": "RETRY", "expected_net_incremental_revenue_minor": 123}],
        selection_result_json={"ai_proposed_action": "PAYMENT_LINK", "deterministic_selected_action": "RETRY"},
        created_at=datetime.now(tz=timezone.utc),
    )
    case = SimpleNamespace(id=case_id, payment_id=payment_id)
    action = SimpleNamespace(id=action_id, status="COMPLETED", discount_percent_offered=0,
                             idempotency_key="action-idem", execution_attempt=2,
                             metadata_json={"execution_reference": "TEST_RETRY", "execution_details": {"mode": "test"}, "economic_evaluation": {"expected_net_incremental_revenue_minor": 123}})
    payment = SimpleNamespace(id=payment_id, amount_minor=50_000, currency="INR", payment_method="UPI", status="CAPTURED")
    attempt = SimpleNamespace(failure_code="TIMEOUT", attempt_number=1)
    outbox = SimpleNamespace(id=outbox_id, status="COMPLETED")
    approval = SimpleNamespace(id=approval_id, decision="APPROVED", actor_id="admin_api_key:hash", reason="approved", correlation_id="cid-approve", created_at=datetime.now(tz=timezone.utc))
    session = AsyncMock()
    session.scalar.side_effect = [audit, case, action, payment, attempt, outbox, approval]

    detail = await ObservabilityService().get_decision_audit(decision_id, session)

    assert detail.correlation_id == "cid-audit"
    assert detail.ai_proposal["recommended_action"] == "PAYMENT_LINK"
    assert detail.selection_result["deterministic_selected_action"] == "RETRY"
    assert detail.approval["actor_id"] == "admin_api_key:hash"
    assert detail.outbox_event_id == outbox_id
    assert detail.execution_reference == "TEST_RETRY"
    assert detail.payment_status == "CAPTURED"
    assert detail.financial_event_id == event_id
    assert not hasattr(detail, "chain_of_thought")
    assert not hasattr(detail, "realized_net_incremental_revenue_minor")
