/**
 * frontend/src/api/client.ts
 *
 * Typed fetch wrapper for the Financial Agent Lab backend.
 *
 * Base URL resolves through the Vite /api proxy in dev (no CORS issue).
 * Throws ApiError on non-2xx responses.
 */

import type {
  ApprovalActionResponse,
  HealthResponse,
  ObservabilitySummaryResponse,
  ReadyResponse,
  RecoveryAuditDetail,
  RunSimulationRequest,
  SimulationRunResponse,
} from './types';

/** Prefix for all API requests — routed through the Vite proxy in dev. */
const API_BASE = '/api';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      // swallow parse errors — use status text
    }
    throw new ApiError(response.status, `${response.status} ${detail}`);
  }

  return response.json() as Promise<T>;
}

async function post<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
  signal?: AbortSignal,
): Promise<T> {
  const reqHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...headers,
  };

  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: reqHeaders,
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const respBody = await response.json();
      detail = respBody?.detail ?? detail;
    } catch {
      // swallow parse errors
    }
    throw new ApiError(response.status, `${response.status} ${detail}`);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API surface
// ---------------------------------------------------------------------------

/** GET /health — liveness check, no DB I/O */
export const fetchHealth = (signal?: AbortSignal) =>
  get<HealthResponse>('/health', signal);

/** GET /ready — readiness check including DB connectivity */
export const fetchReady = (signal?: AbortSignal) =>
  get<ReadyResponse>('/ready', signal);

/** GET /observability/summary — aggregate decision & economic metrics */
export const fetchObservabilitySummary = (signal?: AbortSignal) =>
  get<ObservabilitySummaryResponse>('/observability/summary', signal);

/**
 * GET /observability/recovery/{caseId} — full decision audit for a recovery case.
 * Covers Decision → Policy → Economics → Dispatch → Audit in a single payload.
 */
export const fetchRecoveryCaseAudit = (
  caseId: string,
  signal?: AbortSignal,
) => get<RecoveryAuditDetail>(`/observability/recovery/${caseId}`, signal);

/**
 * POST /recovery-actions/{actionId}/approve — human authorization of a pending action.
 * Transitions status to APPROVED and atomically enqueues transactional outbox dispatch.
 */
export const approveRecoveryAction = (
  actionId: string,
  reason?: string | null,
  apiKey?: string,
  signal?: AbortSignal,
) =>
  post<ApprovalActionResponse>(
    `/recovery-actions/${actionId}/approve`,
    { reason: reason || null },
    apiKey ? { 'X-API-Key': apiKey } : {},
    signal,
  );

/**
 * POST /recovery-actions/{actionId}/reject — managerial rejection of a proposed recovery action.
 * Transitions status to CANCELLED and marks action as not queued.
 */
export const rejectRecoveryAction = (
  actionId: string,
  reason?: string | null,
  apiKey?: string,
  signal?: AbortSignal,
) =>
  post<ApprovalActionResponse>(
    `/recovery-actions/${actionId}/reject`,
    { reason: reason || null },
    apiKey ? { 'X-API-Key': apiKey } : {},
    signal,
  );

/**
 * POST /simulation/run — execute a batch simulation experiment comparing Baseline vs Oracle.
 */
export const runSimulationExperiment = (
  req: RunSimulationRequest = {},
  apiKey?: string,
  signal?: AbortSignal,
) =>
  post<SimulationRunResponse>(
    '/simulation/run',
    {
      scenario_count: req.scenario_count ?? 1000,
      seed: req.seed ?? 42,
      run_name: req.run_name ?? 'lab_simulation_experiment',
    },
    apiKey ? { 'X-API-Key': apiKey } : {},
    signal,
  );
