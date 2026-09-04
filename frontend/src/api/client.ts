/**
 * frontend/src/api/client.ts
 *
 * Typed fetch wrapper for the Financial Agent Lab backend.
 *
 * Base URL resolves through the Vite /api proxy in dev (no CORS issue).
 * Throws ApiError on non-2xx responses.
 */

import type {
  HealthResponse,
  ObservabilitySummaryResponse,
  ReadyResponse,
  RecoveryAuditDetail,
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
