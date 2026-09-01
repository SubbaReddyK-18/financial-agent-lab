"""
domain/intelligence/simulation/generator.py

Reproducible synthetic payment failure scenario generator.

ARCHITECTURAL PRINCIPLES (Block 3, Step 2 & 13):
- Deterministic pseudo-random generation with configurable integer seeds.
- Realistic distributions across failure taxonomies, amount tiers, and customer history.
- Explicit versioning and simulation honesty declarations.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional

from domain.intelligence.models.action_economics import ActionEconomicParameters
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType

# Failure category classification
FAILURE_TAXONOMY = {
    # 1. Technical / Transient (High natural recovery, high retry success)
    "TECHNICAL_TRANSIENT": [
        "GATEWAY_TIMEOUT",
        "NETWORK_ERROR",
        "ISSUER_DOWN",
        "PROCESSING_ERROR",
        "BANK_UNAVAILABLE",
    ],
    # 2. Customer Actionable / Authentication (Moderate natural recovery, high link/notify success)
    "CUSTOMER_ACTIONABLE": [
        "MPIN_EXPIRED",
        "OTP_TIMEOUT",
        "AUTHENTICATION_FAILED",
        "USER_DROPPED",
        "LIMIT_EXCEEDED",
    ],
    # 3. Terminal / Balance (Low natural recovery, low retry success)
    "TERMINAL_BALANCE": [
        "INSUFFICIENT_FUNDS",
        "ACCOUNT_BLOCKED",
        "INVALID_ACCOUNT",
        "CARD_EXPIRED",
        "DO_NOT_HONOR",
    ],
}


@dataclass(frozen=True)
class SyntheticScenario:
    """
    Complete synthetic scenario with embedded ground-truth simulation parameters.
    """

    scenario_id: str
    scenario_version: str
    context: RecoveryContext
    failure_category: str
    ground_truth_natural_recovery_prob: float
    ground_truth_candidate_economics: Mapping[RecoveryActionType, ActionEconomicParameters]


class SyntheticScenarioGenerator:
    """
    Generates realistic, seed-reproducible payment failure scenarios.
    """

    def __init__(self, seed: int = 42, version: str = "v1.0"):
        self.seed = seed
        self.version = version
        self._rng = random.Random(seed)

    def reseed(self, seed: int) -> None:
        """Reset generator seed for deterministic replay."""
        self.seed = seed
        self._rng = random.Random(seed)

    def generate_scenario(self, index: int, merchant_policy: Optional[MerchantRecoveryPolicy] = None) -> SyntheticScenario:
        """
        Generate a single deterministic synthetic scenario.
        """
        scenario_id = f"scn_{self.seed}_{self.version}_{index:06d}"

        # 1. Select failure category and code
        # Distribution: 45% Technical Transient, 35% Customer Actionable, 20% Terminal Balance
        cat_roll = self._rng.random()
        if cat_roll < 0.45:
            category = "TECHNICAL_TRANSIENT"
        elif cat_roll < 0.80:
            category = "CUSTOMER_ACTIONABLE"
        else:
            category = "TERMINAL_BALANCE"

        failure_code = self._rng.choice(FAILURE_TAXONOMY[category])

        # 2. Amount tier distribution (paise)
        # 50% Standard (₹500 - ₹2,500), 30% Micro (₹50 - ₹499), 20% High-Value (₹5,000 - ₹50,000)
        amt_roll = self._rng.random()
        if amt_roll < 0.30:
            amount_minor = self._rng.randint(50_00, 499_00)
        elif amt_roll < 0.80:
            amount_minor = self._rng.randint(500_00, 2500_00)
        else:
            amount_minor = self._rng.randint(5000_00, 50000_00)

        # 3. Payment method distribution (60% UPI, 25% Card, 10% Netbanking, 5% Wallet)
        pm_roll = self._rng.random()
        if pm_roll < 0.60:
            payment_method = PaymentMethod.UPI
        elif pm_roll < 0.85:
            payment_method = PaymentMethod.CARD
        elif pm_roll < 0.95:
            payment_method = PaymentMethod.NETBANKING
        else:
            payment_method = PaymentMethod.WALLET

        # 4. Customer profile
        hist_success_rate = round(self._rng.uniform(0.60, 0.98), 2)
        hist_fail_rate = round(1.0 - hist_success_rate, 2)
        prior_interventions = self._rng.choice([0, 0, 0, 1, 1, 2, 3])
        segment = self._rng.choice(["VIP", "RETURNING", "RETURNING", "NEW", "AT_RISK"])

        customer_profile = CustomerProfile(
            customer_id=uuid.uuid4(),
            historical_payment_count=self._rng.randint(1, 50),
            historical_success_rate=hist_success_rate,
            historical_failure_rate=hist_fail_rate,
            prior_interventions_count=prior_interventions,
            customer_segment=segment,
        )

        # 5. Default Merchant Policy if none provided
        merchant_id = uuid.uuid4()
        if merchant_policy is None:
            merchant_policy = MerchantRecoveryPolicy(
                merchant_id=merchant_id,
                maximum_discount_percent=10,
                maximum_interventions=3,
                cooldown_hours=2,
                high_value_threshold_minor=10000_00,  # ₹10,000
                high_value_requires_approval=True,
            )

        # 6. Payment details
        payment_details = PaymentFailureDetails(
            payment_id=uuid.uuid4(),
            amount_minor=amount_minor,
            currency="INR",
            payment_method=payment_method,
            attempt_count=self._rng.choice([1, 1, 1, 2, 2, 3]),
            failure_code=failure_code,
            failure_reason=f"Synthetic {failure_code} failure",
            failed_at=datetime.now(tz=timezone.utc),
        )

        # 7. Temporal context
        temporal = TemporalContext(
            current_time=datetime.now(tz=timezone.utc),
            hour_of_day=self._rng.randint(0, 23),
            day_of_week=self._rng.randint(0, 6),
            time_since_failure_seconds=self._rng.randint(15, 3600),
            is_cooldown_active=self._rng.choice([False, False, False, False, True]),
        )

        context = RecoveryContext(
            payment=payment_details,
            customer=customer_profile,
            policy=merchant_policy,
            completed_interventions=min(prior_interventions, merchant_policy.maximum_interventions),
            temporal=temporal,
        )

        # 8. Ground Truth Simulation Parameters based on category
        if category == "TECHNICAL_TRANSIENT":
            natural_prob = round(self._rng.uniform(0.25, 0.45), 2)
            retry_prob = round(self._rng.uniform(0.60, 0.85), 2)
            link_prob = round(self._rng.uniform(0.40, 0.60), 2)
            notify_prob = round(self._rng.uniform(0.35, 0.50), 2)
            escalate_prob = round(self._rng.uniform(0.70, 0.90), 2)
        elif category == "CUSTOMER_ACTIONABLE":
            natural_prob = round(self._rng.uniform(0.10, 0.25), 2)
            retry_prob = round(self._rng.uniform(0.20, 0.40), 2)
            link_prob = round(self._rng.uniform(0.55, 0.80), 2)
            notify_prob = round(self._rng.uniform(0.50, 0.70), 2)
            escalate_prob = round(self._rng.uniform(0.65, 0.85), 2)
        else:  # TERMINAL_BALANCE
            natural_prob = round(self._rng.uniform(0.02, 0.08), 2)
            retry_prob = round(self._rng.uniform(0.05, 0.15), 2)
            link_prob = round(self._rng.uniform(0.15, 0.30), 2)
            notify_prob = round(self._rng.uniform(0.10, 0.25), 2)
            escalate_prob = round(self._rng.uniform(0.25, 0.45), 2)

        # Operational intervention costs in paise
        candidate_economics = {
            RecoveryActionType.WAIT: ActionEconomicParameters(
                action_type=RecoveryActionType.WAIT,
                intervention_cost_minor=0,
                estimated_success_probability=natural_prob,
            ),
            RecoveryActionType.RETRY: ActionEconomicParameters(
                action_type=RecoveryActionType.RETRY,
                intervention_cost_minor=20,  # 20 paise
                estimated_success_probability=retry_prob,
            ),
            RecoveryActionType.PAYMENT_LINK: ActionEconomicParameters(
                action_type=RecoveryActionType.PAYMENT_LINK,
                intervention_cost_minor=50,  # 50 paise
                estimated_success_probability=link_prob,
                discount_percent_offered=5 if segment == "VIP" else 0,
            ),
            RecoveryActionType.NOTIFY: ActionEconomicParameters(
                action_type=RecoveryActionType.NOTIFY,
                intervention_cost_minor=15,  # 15 paise
                estimated_success_probability=notify_prob,
            ),
            RecoveryActionType.ESCALATE: ActionEconomicParameters(
                action_type=RecoveryActionType.ESCALATE,
                intervention_cost_minor=500,  # ₹5.00
                estimated_success_probability=escalate_prob,
            ),
        }

        return SyntheticScenario(
            scenario_id=scenario_id,
            scenario_version=self.version,
            context=context,
            failure_category=category,
            ground_truth_natural_recovery_prob=natural_prob,
            ground_truth_candidate_economics=candidate_economics,
        )

    def generate_batch(self, count: int, policy: Optional[MerchantRecoveryPolicy] = None) -> list[SyntheticScenario]:
        """Generate a batch of deterministic scenarios."""
        return [self.generate_scenario(i, policy) for i in range(count)]
