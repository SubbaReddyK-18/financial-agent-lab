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

// ---------------------------------------------------------------------------
// Recovery Case Audit — GET /observability/recovery/{recovery_case_id}
//                       GET /observability/decisions/{decision_id}
// ---------------------------------------------------------------------------

/**
 * Contextual snapshot captured at decision time from the live payment/customer record.
 * All amounts are integer minor units (paise).
 */
export interface ObservableContext {
  payment_id: string;
  /** Payment amount in paise */
  amount_minor: number;
  currency: string;
  /** e.g. "CARD", "UPI", "NET_BANKING" */
  payment_method: string;
  /** e.g. "GATEWAY_TIMEOUT", "INSUFFICIENT_FUNDS" */
  failure_code: string;
  attempt_count: number;
  customer_segment: string;
  customer_historical_success_rate: number;
  is_cooldown_active: boolean;
  is_business_hours: boolean;
}

/**
 * Economic model evaluation output produced by EconomicEngine.
 * All monetary values are integer minor units (paise). Divide by 100 for INR display.
 */
export interface EconomicEvaluation {
  /** Gross revenue model projection (paise) */
  expected_gross_revenue_minor: number;
  /** Natural recovery baseline projection (paise) */
  expected_natural_revenue_minor: number;
  /** Incremental over baseline (paise) */
  expected_incremental_revenue_minor: number;
  /** Discount / retry intervention cost (paise) */
  intervention_cost_minor: number;
  /** Net of intervention + inference costs (paise) */
  expected_net_incremental_revenue_minor: number;
  /** Estimated LLM inference cost (paise) */
  estimated_llm_cost_minor: number;
}

/**
 * Full structured audit record returned by
 *   GET /observability/recovery/{recovery_case_id}
 *   GET /observability/decisions/{decision_id}
 *
 * Covers Decision → Policy → Economics → Dispatch → Audit in a single payload.
 */
export interface RecoveryAuditDetail {
  decision_id: string;
  /** Same as the recovery case UUID when fetched via /recovery/{id} */
  scenario_id: string | null;
  recovery_case_id: string | null;
  payment_id: string | null;
  correlation_id: string | null;
  decision_request_id: string | null;
  audit_schema_version: string;
  /** ISO 8601 UTC timestamp */
  created_at: string;

  // AI provenance
  provider: string;
  model: string;
  prompt_version: string;

  // Decision output
  observable_context: ObservableContext | null;
  proposed_action: string;
  confidence: number;
  /** "LOW" | "MEDIUM" | "HIGH" */
  uncertainty: string;
  reasoning_codes: string[];

  // Policy gate
  policy_approved: boolean;
  requires_human_review: boolean;
  fallback_used: boolean;
  fallback_reason: string | null;
  final_action: string;
  discount_percent_offered: number;

  // Economic evaluation (null when record pre-dates EconomicEngine)
  economic_evaluation: EconomicEvaluation | null;

  // Execution / dispatch
  execution_status: string | null;
  execution_reference: string | null;
  execution_details: Record<string, unknown> | null;

  // Recovery action linkage
  recovery_action_id: string | null;
  action_idempotency_key: string | null;

  // Outbox / dispatch
  outbox_event_id: string | null;
  outbox_status: string | null;
  execution_attempt: number | null;

  // Approval record (null when no human approval is required)
  approval: Record<string, unknown> | null;

  // Payment linkage
  financial_event_id: string | null;
  payment_status: string | null;

  // Latency / LLM cost
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_llm_cost_minor: number | null;

  // Internal JSON blobs (available but not typed beyond object)
  ai_proposal: Record<string, unknown> | null;
  proposal_validation: Record<string, unknown> | null;
  policy_result: Record<string, unknown> | null;
  authorization_result: Record<string, unknown> | null;
  economic_candidates: unknown[];
  selection_result: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Recovery Action Approvals — POST /recovery-actions/{action_id}/approve
//                           POST /recovery-actions/{action_id}/reject
// ---------------------------------------------------------------------------

export interface ApprovalActionRequest {
  reason?: string | null;
}

export interface ApprovalActionResponse {
  action_id: string;
  status: 'APPROVED' | 'CANCELLED';
  execution: 'queued' | 'not_queued';
}
