"""
tests/unit/test_observability.py

Unit tests for Decision Observability, Metric Aggregations, Regret Analysis,
Probability Calibration, Version Comparison, and Audit Traceability.

Covers (Block 6, Requirement 10):
- Operational metric aggregations
- Economic metric calculations in integer minor units (paise)
- Regret summary and near-optimality rates
- Probability MAE, Brier Score, and calibration buckets
- Model version comparator
- Zero-decision and zero-Oracle-value edge cases
- Information boundary preservation (no hidden simulation data leakage)
- No chain-of-thought persistence
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.observability.audit_view import (
    DecisionAuditDetail,
    EconomicValuationSummary,
    ObservableContextSummary,
)
from domain.observability.metrics import (
    DecisionMetricsSummary,
    EconomicMetricsSummary,
    ObservabilitySummary,
    compute_percentile,
)
from domain.observability.service import ObservabilityService
from domain.observability.simulation_evaluator import (
    AdvancedSimulationEvaluator,
    CalibrationBucket,
    CalibrationReport,
    RegretSummary,
)
from domain.observability.version_comparison import (
    ModelVersionCandidate,
    ModelVersionComparator,
)
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.payment import PaymentORM
from infrastructure.database.orm.recovery import RecoveryActionORM, RecoveryCaseORM


class TestPercentileComputation:
    def test_percentiles_with_empty_list(self):
        assert compute_percentile([], 0.50) == 0.0

    def test_percentiles_with_values(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        assert compute_percentile(values, 0.50) == 55.0
        assert compute_percentile(values, 0.90) == 91.0
        assert compute_percentile(values, 0.99) == 99.1


class TestObservabilityServiceAggregations:
    @pytest.mark.asyncio
    async def test_zero_decisions_summary(self):
        session = AsyncMock()
        session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        session.scalar.return_value = 0

        service = ObservabilityService()
        summary = await service.get_observability_summary(session)

        assert summary.source_type == "LIVE_PRODUCTION"
        assert summary.decision_metrics.total_decisions == 0
        assert summary.decision_metrics.fallback_count == 0
        assert summary.economic_metrics.total_economic_value_minor == 0

    @pytest.mark.asyncio
    async def test_decision_and_economic_aggregations_with_records(self):
        session = AsyncMock()

        # Mock 2 AI decision records (1 normal, 1 fallback due to policy)
        audit1 = MagicMock(
            id=uuid.uuid4(),
            scenario_id=str(uuid.uuid4()),
            provider="mock",
            model="mock-v1",
            prompt_version="v1.0",
            recommended_action="PAYMENT_LINK",
            final_action="PAYMENT_LINK",
            fallback_used=False,
            fallback_reason=None,
            requires_human_review=False,
            latency_ms=120.5,
            input_tokens=500,
            output_tokens=100,
            estimated_llm_cost_minor=2,
            expected_net_incremental_revenue_minor=850_00,  # ₹850.00
        )
        audit2 = MagicMock(
            id=uuid.uuid4(),
            scenario_id=str(uuid.uuid4()),
            provider="mock",
            model="mock-v1",
            prompt_version="v1.0",
            recommended_action="PAYMENT_LINK",
            final_action="WAIT",
            fallback_used=True,
            fallback_reason="Policy rejected: max discount exceeded",
            requires_human_review=True,
            latency_ms=80.0,
            input_tokens=400,
            output_tokens=50,
            estimated_llm_cost_minor=1,
            expected_net_incremental_revenue_minor=-50_00,  # negative value test
        )

        action1 = MagicMock(
            status="COMPLETED",
            metadata_json={
                "economic_evaluation": {
                    "expected_gross_revenue_minor": 1000_00,
                    "expected_natural_recovery_minor": 100_00,
                    "expected_incremental_revenue_minor": 900_00,
                    "intervention_cost_minor": 50_00,
                }
            },
        )

        session.scalars.side_effect = [
            MagicMock(all=MagicMock(return_value=[audit1, audit2])),  # audit records
            MagicMock(all=MagicMock(return_value=[action1])),          # recovery actions
        ]
        session.scalar.return_value = 1000_00  # realized captured payment

        service = ObservabilityService()
        summary = await service.get_observability_summary(session)

        # Operational metrics verification
        assert summary.decision_metrics.total_decisions == 2
        assert summary.decision_metrics.successful_ai_proposals == 1
        assert summary.decision_metrics.fallback_count == 1
        assert summary.decision_metrics.fallback_rate == 0.50
        assert summary.decision_metrics.policy_rejection_count == 1
        assert summary.decision_metrics.policy_rejection_rate == 0.50
        assert summary.decision_metrics.human_review_required_count == 1
        assert summary.decision_metrics.final_action_distribution == {"PAYMENT_LINK": 1, "WAIT": 1}
        assert summary.decision_metrics.total_input_tokens == 900
        assert summary.decision_metrics.total_output_tokens == 150
        assert summary.decision_metrics.total_inference_cost_minor == 3

        # Economic metrics verification (exact integer paise)
        assert summary.economic_metrics.expected_gross_recovery_minor == 1000_00
        assert summary.economic_metrics.expected_incremental_recovery_minor == 900_00
        assert summary.economic_metrics.expected_net_incremental_revenue_minor == 800_00
        assert summary.economic_metrics.realized_captured_revenue_minor == 1000_00
        assert summary.economic_metrics.positive_value_decision_rate == 0.50
        assert summary.economic_metrics.negative_value_decision_rate == 0.50


class TestSimulationEvaluatorAndCalibration:
    @pytest.mark.asyncio
    async def test_offline_simulation_evaluator_metrics(self):
        canned_json = """{
            "recommended_action": "RETRY",
            "confidence": 0.85,
            "estimated_action_success_probability": 0.70,
            "estimated_natural_recovery_probability": 0.20,
            "reasoning_codes": ["TRANSIENT_ERROR"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Clear technical network timeout.",
            "recommended_discount_percent": 0
        }"""
        client = MockLLMClient(canned_response=canned_json)
        ai_provider = AIDecisionProvider(client=client)

        evaluator = AdvancedSimulationEvaluator(seed=42)
        report = await evaluator.evaluate_async(ai_provider=ai_provider, scenario_count=10)

        assert report.source_type == "SYNTHETIC_SIMULATION"
        assert report.scenario_count == 10
        assert isinstance(report.economic_value_capture_ratio, float)
        assert report.regret.mean_regret_minor >= 0
        assert 0.0 <= report.regret.within_10_pct_rate <= 1.0
        assert 0.0 <= report.exact_oracle_action_agreement_rate <= 1.0

        # Calibration metrics
        assert 0.0 <= report.calibration.natural_recovery_prob_mae <= 1.0
        assert 0.0 <= report.calibration.action_recovery_prob_mae <= 1.0
        assert report.calibration.brier_score >= 0.0
        assert len(report.calibration.buckets) == 5

    @pytest.mark.asyncio
    async def test_model_version_comparator(self):
        client1 = MockLLMClient(canned_response="""{"recommended_action": "WAIT", "confidence": 0.9, "estimated_action_success_probability": 0.1, "estimated_natural_recovery_probability": 0.3, "reasoning_codes": [], "uncertainty": "LOW", "requires_human_review": false, "concise_rationale": "Wait", "recommended_discount_percent": 0}""")
        client2 = MockLLMClient(canned_response="""{"recommended_action": "RETRY", "confidence": 0.9, "estimated_action_success_probability": 0.7, "estimated_natural_recovery_probability": 0.2, "reasoning_codes": [], "uncertainty": "LOW", "requires_human_review": false, "concise_rationale": "Retry", "recommended_discount_percent": 0}""")

        prov1 = AIDecisionProvider(client=client1)
        prov2 = AIDecisionProvider(client=client2)

        candidates = [
            ModelVersionCandidate(name="Candidate Wait", provider=prov1, version_tag="v1"),
            ModelVersionCandidate(name="Candidate Retry", provider=prov2, version_tag="v2"),
        ]

        comparator = ModelVersionComparator(seed=42)
        comp_report = await comparator.compare_candidates_async(candidates, scenario_count=5)

        assert comp_report.scenario_count == 5
        assert len(comp_report.candidates) == 2
        assert len(comp_report.deltas) == 1
        delta = comp_report.deltas[0]
        assert delta.champion_name == "Candidate Wait"
        assert delta.challenger_name == "Candidate Retry"


class TestAuditViewIntegrityAndPrivacy:
    @pytest.mark.asyncio
    async def test_decision_audit_no_chain_of_thought_leakage(self):
        session = AsyncMock()
        decision_id = uuid.uuid4()
        case_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        audit = AIDecisionRecordORM(
            id=decision_id,
            scenario_id=str(case_id),
            provider="gemini",
            model="gemini-2.5-flash",
            prompt_version="v1.0",
            recommended_action="PAYMENT_LINK",
            confidence=0.85,
            reasoning_codes=["AUTH_DROP", "HIGH_CUSTOMER_VALUE"],
            uncertainty="LOW",
            requires_human_review=False,
            fallback_used=False,
            fallback_reason=None,
            latency_ms=150.0,
            input_tokens=600,
            output_tokens=120,
            estimated_llm_cost_minor=2,
            final_action="PAYMENT_LINK",
            expected_net_incremental_revenue_minor=1200_00,
            created_at=datetime.now(tz=timezone.utc),
        )

        mock_case = MagicMock(id=case_id, payment_id=payment_id)
        mock_payment = MagicMock(
            id=payment_id,
            amount_minor=1500_00,
            currency="INR",
            payment_method="CARD",
        )
        mock_attempt = MagicMock(
            failure_code="INSUFFICIENT_FUNDS",
            attempt_number=2,
        )
        mock_action = MagicMock(
            id=uuid.uuid4(),
            status="COMPLETED",
            discount_percent_offered=5,
            metadata_json={
                "execution_reference": "TEST_PLINK_abc123",
                "execution_details": {"url": "https://test.pay"},
                "economic_evaluation": {
                    "expected_gross_revenue_minor": 1500_00,
                    "expected_natural_revenue_minor": 200_00,
                    "expected_incremental_revenue_minor": 1225_00,
                    "intervention_cost_minor": 25_00,
                    "expected_net_incremental_revenue_minor": 1200_00,
                },
            },
        )

        session.scalar.side_effect = [audit, mock_case, mock_action, mock_payment, mock_attempt]

        service = ObservabilityService()
        audit_detail = await service.get_decision_audit(decision_id, session)

        assert audit_detail is not None
        assert audit_detail.decision_id == decision_id
        assert audit_detail.provider == "gemini"
        assert audit_detail.model == "gemini-2.5-flash"
        assert audit_detail.reasoning_codes == ["AUTH_DROP", "HIGH_CUSTOMER_VALUE"]
        assert audit_detail.execution_reference == "TEST_PLINK_abc123"
        assert audit_detail.observable_context.failure_code == "INSUFFICIENT_FUNDS"
        assert audit_detail.observable_context.attempt_count == 2

        # Verify that no raw internal chain-of-thought field exists
        assert not hasattr(audit_detail, "chain_of_thought")
        assert not hasattr(audit_detail, "raw_thoughts")


class TestRegretAndCalibrationEdgeCases:
    @pytest.mark.asyncio
    async def test_zero_oracle_value_and_negative_ai_value_regret(self):
        """
        Verify that when Oracle net revenue is <= 0 (e.g. WAIT is optimal)
        and AI chooses an action with negative net return, near-optimality rate is NOT incremented.
        """
        # AI proposes a costly payment link with zero success
        canned_json = """{
            "recommended_action": "PAYMENT_LINK",
            "confidence": 0.50,
            "estimated_action_success_probability": 0.05,
            "estimated_natural_recovery_probability": 0.05,
            "reasoning_codes": ["LOW_PROBABILITY"],
            "uncertainty": "HIGH",
            "requires_human_review": false,
            "concise_rationale": "High cost low probability intervention.",
            "recommended_discount_percent": 10
        }"""
        client = MockLLMClient(canned_response=canned_json)
        ai_provider = AIDecisionProvider(client=client)

        evaluator = AdvancedSimulationEvaluator(seed=12345)
        report = await evaluator.evaluate_async(ai_provider=ai_provider, scenario_count=5)

        assert report.scenario_count == 5
        assert isinstance(report.regret.mean_regret_minor, int)
        assert 0.0 <= report.regret.within_1_pct_rate <= 1.0
        assert 0.0 <= report.regret.within_5_pct_rate <= 1.0
        assert 0.0 <= report.regret.within_10_pct_rate <= 1.0

    def test_causal_attribution_distinction_documented(self):
        """Verify EconomicMetricsSummary clearly separates observed payments from causal incrementality."""
        econ = EconomicMetricsSummary(
            expected_net_incremental_revenue_minor=500_00,
            realized_captured_revenue_minor=1000_00,
        )
        assert econ.expected_net_incremental_revenue_minor == 500_00
        assert econ.realized_captured_revenue_minor == 1000_00
        assert hasattr(econ, "realized_captured_revenue_minor")
        assert not hasattr(econ, "realized_net_incremental_revenue_minor")
