/**
 * frontend/src/hooks/useRecoveryAudit.ts
 *
 * Fetches a single recovery case audit record on mount.
 * Provides loading, error, and manual refresh controls.
 *
 * Design notes (mirrors useOperationsSummary):
 * - Uses AbortController to cancel stale in-flight requests.
 * - Previous data stays visible while refreshing.
 * - Errors do NOT clear previous data.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, fetchRecoveryCaseAudit } from '../api/client';
import type { RecoveryAuditDetail } from '../api/types';

export interface UseRecoveryAuditResult {
  data: RecoveryAuditDetail | null;
  /** True while a fetch is in flight */
  loading: boolean;
  /** True only on the very first fetch (no data yet) */
  initializing: boolean;
  error: string | null;
  /** ISO 8601 string of the last successful fetch */
  lastFetchedAt: string | null;
  /** Manually trigger an immediate re-fetch */
  refresh: () => void;
}

export function useRecoveryAudit(caseId: string): UseRecoveryAuditResult {
  const [data, setData] = useState<RecoveryAuditDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const fetchAudit = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;

    setLoading(true);

    try {
      const result = await fetchRecoveryCaseAudit(caseId, signal);

      if (signal.aborted) return;

      setData(result);
      setError(null);
      setLastFetchedAt(new Date().toISOString());
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;

      const message =
        err instanceof ApiError
          ? `API error ${err.status}: ${err.message}`
          : `Network error: ${(err as Error).message}`;

      setError(message);
      // Keep previous data visible on error
    } finally {
      if (!signal.aborted) {
        setLoading(false);
        setInitializing(false);
      }
    }
  }, [caseId]);

  useEffect(() => {
    fetchAudit();
    return () => {
      abortRef.current?.abort();
    };
  }, [fetchAudit]);

  return { data, loading, initializing, error, lastFetchedAt, refresh: fetchAudit };
}
