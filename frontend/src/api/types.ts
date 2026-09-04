/**
 * frontend/src/api/types.ts
 *
 * Typed interfaces matching the backend JSON response shapes exactly.
 * Monetary values are always integer minor units (paise); convert only at display time.
 * See: apps/api/routes/observability.py, apps/api/routes/health.py
 */

// ---------------------------------------------------------------------------
// Health & Readiness
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: 'ok';
  service: string;
  environment: string;
}

export interface ReadyResponse {
  status: 'ready' | 'unready';
  database: 'connected' | 'unreachable';
  environment: string;
  /** Only present when status === 'ready' */
  ai_provider?: string;
}

// ---------------------------------------------------------------------------
// Observability Summary — GET /observability/summary
// ---------------------------------------------------------------------------

/**
 * Decision metrics aggregated across all AIDecisionRecordORM rows.
 * All counts are integers; all rates are floats in [0, 1].
 * Latency values are in milliseconds.
 */
export interface DecisionMetrics {
  total_decisions: number;
  ai_proposals_attempted: number;
  successful_ai_proposals: number;
  fallback_count: number;
  fallback_rate: number;
  policy_rejection_count: number;
  policy_rejection_rate: number;

  /** key: RecoveryActionType string, value: count */
  final_action_distribution: Record<string, number>;
  /** key: RecoveryActionType string, value: count */
  ai_proposed_action_distribution: Record<string, number>;
  /** key: RecoveryActionType string, value: count */
  fallback_action_distribution: Record<string, number>;

  execution_success_count: number;
  execution_failure_count: number;
  human_review_required_count: number;

  /** RecoveryActionStatus lifecycle counts */
  actions_proposed: number;
  actions_approved: number;
  actions_executing: number;
  actions_completed: number;
  actions_failed: number;
  actions_cancelled: number;
  actions_expired: number;
  actions_superseded: number;

  total_retries: number;
  pending_outbox_count: number;
  outbox_processing_count: number;
  outbox_failed_count: number;

  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;

  avg_input_tokens: number;
  avg_output_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  /** LLM inference cost in integer paise */
  total_inference_cost_minor: number;
}

/**
 * Economic metrics computed from authoritative DB records.
 * ALL monetary fields are integer minor units (paise). Divide by 100 for INR display.
 *
 * IMPORTANT DISTINCTION:
 *   realized_captured_revenue_minor — OBSERVED: sum of CAPTURED payment amounts
 *     associated with recovery cases. NOT causal incremental revenue; no holdout
 *     counterfactual exists in single-stream production.
 *   expected_net_incremental_revenue_minor — PROJECTED: deterministic EconomicEngine
 *     model estimate of net incremental revenue above natural baseline.
 */
export interface EconomicMetrics {
  /** Gross revenue model projection (paise) */
  expected_gross_recovery_minor: number;
  /** Natural recovery baseline projection (paise) */
  expected_natural_recovery_minor: number;
  /** Incremental over baseline projection (paise) */
  expected_incremental_recovery_minor: number;
  /** Discount/retry intervention cost (paise) */
  intervention_cost_minor: number;
  /** LLM inference cost (paise) */
  ai_inference_cost_minor: number;
  /** Net of intervention + inference costs (paise) — EconomicEngine projection */
  expected_net_incremental_revenue_minor: number;
  /**
   * OBSERVED: Sum of amount_minor where PaymentORM.status = CAPTURED
   * for payments that have a RecoveryCase. NOT causally attributed incremental revenue.
   */
  realized_captured_revenue_minor: number;
  /** total_economic_value = expected_net_incremental - ai_inference_cost (paise) */
  total_economic_value_minor: number;
  /** Per-decision average economic value (paise) */
  avg_economic_value_minor: number;
  positive_value_decision_rate: number;
  negative_value_decision_rate: number;
}

export interface ObservabilitySummaryResponse {
  /** Always "LIVE_PRODUCTION" for this endpoint */
  source_type: 'LIVE_PRODUCTION' | 'SYNTHETIC_SIMULATION';
  generated_at: string; // ISO 8601 UTC
  decision_metrics: DecisionMetrics;
  economic_metrics: EconomicMetrics;
}
