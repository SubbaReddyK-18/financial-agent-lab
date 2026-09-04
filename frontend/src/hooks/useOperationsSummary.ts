/**
 * frontend/src/hooks/useOperationsSummary.ts
 *
 * Polling hook for the Operations Control Room.
 * Fetches /observability/summary, /health, and /ready on mount and at a
 * configurable interval.
 *
 * Design notes:
 * - Uses AbortController so in-flight requests are cancelled on unmount / before
 *   the next poll fires, preventing stale-state races.
 * - Keeps previous data visible while refreshing so the UI never blanks out.
 * - Errors do NOT clear previous data; they set an error state alongside it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  fetchHealth,
  fetchObservabilitySummary,
  fetchReady,
} from '../api/client';
import type {
  HealthResponse,
  ObservabilitySummaryResponse,
  ReadyResponse,
} from '../api/types';

export interface OperationsData {
  summary: ObservabilitySummaryResponse | null;
  health: HealthResponse | null;
  ready: ReadyResponse | null;
}

export interface UseOperationsSummaryResult {
  data: OperationsData;
  loading: boolean;
  /** True only on the very first fetch (no data yet) */
  initializing: boolean;
  error: string | null;
  /** ISO 8601 string of the last successful fetch */
  lastFetchedAt: string | null;
  /** Manually trigger an immediate refresh */
  refresh: () => void;
}

const DEFAULT_POLL_INTERVAL_MS = 30_000; // 30 s — lightweight, read-only queries

export function useOperationsSummary(
  pollIntervalMs: number = DEFAULT_POLL_INTERVAL_MS,
): UseOperationsSummaryResult {
  const [data, setData] = useState<OperationsData>({
    summary: null,
    health: null,
    ready: null,
  });
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  // Stable ref to avoid re-registering the interval on every render
  const abortRef = useRef<AbortController | null>(null);

  const fetchAll = useCallback(async () => {
    // Cancel any previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;

    setLoading(true);

    try {
      // Fire all three in parallel — they are independent endpoints
      const [summary, health, ready] = await Promise.all([
        fetchObservabilitySummary(signal),
        fetchHealth(signal),
        fetchReady(signal),
      ]);

      if (signal.aborted) return; // component unmounted before we got a response

      setData({ summary, health, ready });
      setError(null);
      setLastFetchedAt(new Date().toISOString());
    } catch (err) {
      if ((err as Error).name === 'AbortError') return; // intentional cancel

      const message =
        err instanceof ApiError
          ? `API error: ${err.message}`
          : `Network error: ${(err as Error).message}`;

      setError(message);
      // Do NOT clear previous data on error — keep showing stale values
    } finally {
      if (!signal.aborted) {
        setLoading(false);
        setInitializing(false);
      }
    }
  }, []);

  // Kick off immediately on mount, then poll
  useEffect(() => {
    fetchAll();
    const intervalId = setInterval(fetchAll, pollIntervalMs);

    return () => {
      clearInterval(intervalId);
      abortRef.current?.abort();
    };
  }, [fetchAll, pollIntervalMs]);

  return { data, loading, initializing, error, lastFetchedAt, refresh: fetchAll };
}
