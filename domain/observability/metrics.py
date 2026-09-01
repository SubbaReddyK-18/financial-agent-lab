"""
domain/observability/metrics.py

Data structures for deterministic decision metrics and economic metrics.

ARCHITECTURAL PRINCIPLES (Block 6, Requirement 1 & 2):
1. Metrics are strictly derived from authoritative database records and deterministic engines.
2. All monetary values are integer minor units (paise) — no floating-point currency representation.
3. Live production metrics and synthetic simulation evaluations are explicitly partitioned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class DecisionMetricsSummary:
    """Aggregated operational and health metrics for recovery decisions."""

    total_decisions: int = 0
    ai_proposals_attempted: int = 0
    successful_ai_proposals: int = 0
    fallback_count: int = 0
    fallback_rate: float = 0.0
    policy_rejection_count: int = 0
    policy_rejection_rate: float = 0.0

    # Action Distributions
    final_action_distribution: dict[str, int] = field(default_factory=dict)
    ai_proposed_action_distribution: dict[str, int] = field(default_factory=dict)
    fallback_action_distribution: dict[str, int] = field(default_factory=dict)

    # Execution & Control Plane Health
    execution_success_count: int = 0
    execution_failure_count: int = 0
    human_review_required_count: int = 0

    # Action Control Plane Lifecycle Stats
    actions_proposed: int = 0
    actions_approved: int = 0
    actions_executing: int = 0
    actions_completed: int = 0
    actions_failed: int = 0
    actions_cancelled: int = 0
    actions_expired: int = 0
    actions_superseded: int = 0
    total_retries: int = 0
    pending_outbox_count: int = 0
    outbox_processing_count: int = 0
    outbox_failed_count: int = 0

    # Latency Metrics (milliseconds)
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Token & Cost Metrics
    avg_input_tokens: float = 0.0
    avg_output_tokens: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_inference_cost_minor: int = 0  # in paise


@dataclass(frozen=True)
class EconomicMetricsSummary:
    """
    Aggregated economic metrics computed in authoritative integer minor units (paise).

    NOTE ON CAUSAL ATTRIBUTION (Block 6 Audit):
    - expected_* metrics reflect deterministic EconomicEngine model projections.
    - realized_captured_revenue_minor reflects observed successful payment captures
      associated with recovery cases. In live single-stream production, causal incremental
      attribution cannot be isolated without counterfactual holdouts and is thus not claimed.
    """

    expected_gross_recovery_minor: int = 0
    expected_natural_recovery_minor: int = 0
    expected_incremental_recovery_minor: int = 0
    intervention_cost_minor: int = 0
    ai_inference_cost_minor: int = 0
    expected_net_incremental_revenue_minor: int = 0
    realized_captured_revenue_minor: int = 0
    total_economic_value_minor: int = 0
    avg_economic_value_minor: int = 0
    positive_value_decision_rate: float = 0.0
    negative_value_decision_rate: float = 0.0


@dataclass(frozen=True)
class ObservabilitySummary:
    """Top-level summary combining decision health and economic performance."""

    decision_metrics: DecisionMetricsSummary
    economic_metrics: EconomicMetricsSummary
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source_type: str = "LIVE_PRODUCTION"  # "LIVE_PRODUCTION" or "SYNTHETIC_SIMULATION"


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute exact or linear-interpolated percentile from a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_vals[int(k)], 2)
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return round(d0 + d1, 2)
