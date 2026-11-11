'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, errorMessage } from './api/errors';

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | Error | undefined;
  loading: boolean;
  /** true when a refresh failed but older data is still being shown */
  stale: boolean;
  updatedAt: number | null;
  refetch: () => void;
}

interface Internal<T> { key: string | null; data?: T; error?: ApiError | Error; loading: boolean; updatedAt: number | null }

export interface ApiOptions {
  /** Re-fetch on an interval (ms) while the tab is visible. */
  pollMs?: number;
  /** Re-fetch when the window regains focus. Default true. */
  refetchOnFocus?: boolean;
}

/**
 * Fetch hook with cancellation, explicit loading/error state and stale-data retention.
 * `key` identifies the resource (include the user + ids). `null` disables the request.
 */
export function useApi<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>, opts: ApiOptions = {}): ApiState<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<Internal<T>>({ key, loading: key !== null, updatedAt: null });

  useEffect(() => {
    if (key === null) { setState({ key, loading: false, updatedAt: null }); return; }
    const ac = new AbortController();
    setState((prev) => ({ key, data: prev.key === key ? prev.data : undefined, error: undefined, loading: true,
      updatedAt: prev.key === key ? prev.updatedAt : null }));
    fetcherRef.current(ac.signal).then(
      (data) => { if (!ac.signal.aborted) setState({ key, data, loading: false, updatedAt: Date.now() }); },
      (error: unknown) => {
        if (ac.signal.aborted || (error instanceof ApiError && error.kind === 'aborted')) return;
        setState((prev) => ({ key, data: prev.key === key ? prev.data : undefined, error: error as Error,
          loading: false, updatedAt: prev.key === key ? prev.updatedAt : null }));
      });
    return () => ac.abort();
  }, [key, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  const { pollMs, refetchOnFocus = true } = opts;
  useEffect(() => {
    if (key === null || !pollMs) return;
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') refetch(); }, pollMs);
    return () => window.clearInterval(t);
  }, [key, pollMs, refetch]);
  useEffect(() => {
    if (key === null || !refetchOnFocus) return;
    const onFocus = () => refetch();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [key, refetchOnFocus, refetch]);

  const current = state.key === key;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: current ? state.loading : key !== null,
    stale: current && !!state.error && state.data !== undefined,
    updatedAt: current ? state.updatedAt : null,
    refetch,
  };
}

/**
 * Prevents duplicate submissions: while one call is in flight, further calls are ignored (return undefined).
 * The ref flips synchronously so a double-tap in the same frame cannot slip through before React re-renders.
 */
export function useSingleFlight<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setPending(true);
    try {
      return await fnRef.current(...args);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }, []);
  return { run, pending };
}

/** A single-flight command with its own error message; errors are captured, never thrown to React. */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [error, setError] = useState<string | null>(null);
  const flight = useSingleFlight(async (...args: A) => {
    setError(null);
    try {
      return await fn(...args);
    } catch (e) {
      setError(errorMessage(e));
      return undefined;
    }
  });
  return { run: flight.run, pending: flight.pending, error, clearError: () => setError(null) };
}
