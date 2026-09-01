"""
domain/observability/audit_view.py

Structured decision inspection data models for auditing end-to-end recovery decisions.

ARCHITECTURAL PRINCIPLES (Block 6, Requirement 5):
1. Reconstructs the complete lifecycle from authoritative database records.
2. Surfaces observable context, AI proposal, policy gate outcome, economic valuation,
   and test execution reference.
3. No raw chain-of-thought is ever persisted or exposed; only concise rationale and reasoning codes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class ObservableContextSummary:
    """Summary of the observable context presented to the decision system."""

    payment_id: uuid.UUID
    amount_minor: int
    currency: str
    payment_method: str
    failure_code: str
    attempt_count: int
    customer_segment: str
    customer_historical_success_rate: float
    is_cooldown_active: bool
    is_business_hours: bool


@dataclass(frozen=True)
class EconomicValuationSummary:
    """Authoritative economic breakdown computed in integer minor units (paise)."""

    expected_gross_revenue_minor: int
    expected_natural_revenue_minor: int
    expected_incremental_revenue_minor: int
    intervention_cost_minor: int
    expected_net_incremental_revenue_minor: int
    estimated_llm_cost_minor: int


@dataclass(frozen=True)
class DecisionAuditDetail:
    """Complete end-to-end audit record for a single recovery decision."""

    decision_id: uuid.UUID
    scenario_id: str
    recovery_case_id: Optional[uuid.UUID]
    payment_id: Optional[uuid.UUID]
    correlation_id: Optional[str]
    created_at: datetime

    # Model & Provider Attribution
    provider: str
    model: str
    prompt_version: str

    # Context & Proposal
    observable_context: Optional[ObservableContextSummary]
    proposed_action: str
    confidence: float
    uncertainty: str
    reasoning_codes: list[str] = field(default_factory=list)

    # Policy & Fallback Verification
    policy_approved: bool = True
    requires_human_review: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None

    # Final Approved Outcome & Economics
    final_action: str = "WAIT"
    discount_percent_offered: int = 0
    economic_evaluation: Optional[EconomicValuationSummary] = None

    # Execution Details
    execution_status: str = "COMPLETED"
    execution_reference: Optional[str] = None
    execution_details: dict[str, Any] = field(default_factory=dict)

    # Operational Telemetry
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_llm_cost_minor: int = 0

    # Durable Block 9 snapshots and linked authoritative records.
    decision_request_id: Optional[uuid.UUID] = None
    audit_schema_version: Optional[str] = None
    ai_proposal: Optional[dict[str, Any]] = None
    proposal_validation: dict[str, Any] = field(default_factory=dict)
    policy_result: dict[str, Any] = field(default_factory=dict)
    authorization_result: dict[str, Any] = field(default_factory=dict)
    economic_candidates: list[dict[str, Any]] = field(default_factory=list)
    selection_result: dict[str, Any] = field(default_factory=dict)
    recovery_action_id: Optional[uuid.UUID] = None
    action_idempotency_key: Optional[str] = None
    outbox_event_id: Optional[uuid.UUID] = None
    outbox_status: Optional[str] = None
    execution_attempt: Optional[int] = None
    approval: Optional[dict[str, Any]] = None
    financial_event_id: Optional[uuid.UUID] = None
    payment_status: Optional[str] = None
