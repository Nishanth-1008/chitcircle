import { API_BASE } from '../config';
import type { Actor } from '../permissions';
import { ApiError, detailFrom, kindForStatus } from './errors';

export interface ApiContext {
  actor: Actor | null;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * One typed entry point for every backend call.
 * - All calls go to the same-origin /api/backend/* proxy (no demo mode, no demo fixtures).
 * - State-changing methods (POST/PUT/PATCH/DELETE) send an Idempotency-Key so the
 *   backend can deduplicate retries. Read-only GET calls do not.
 * The X-Actor-* headers are the backend's development auth stub. They are sent for identification only and are
 * NEVER used by this client as proof of permission.
 */
export async function request<T>(ctx: ApiContext, path: string, opts: RequestOptions = {}): Promise<T> {
  if (opts.signal?.aborted) throw new ApiError('aborted', 0, 'Request cancelled');
  if (!ctx.actor) throw new ApiError('unauthorized', 401, 'Sign in to continue.');

  const method = opts.method ?? 'GET';
  const isStateChanging = method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE';

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      signal: opts.signal,
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(isStateChanging ? { 'Idempotency-Key': crypto.randomUUID() } : {}),
        'X-Actor-Id': ctx.actor.id,
        'X-Actor-Role': ctx.actor.role,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') throw new ApiError('aborted', 0, 'Request cancelled');
    throw new ApiError('network', 0, 'Network request failed');
  }

  let parsed: unknown = null;
  const text = await res.text();
  if (text) {
    try { parsed = JSON.parse(text); } catch { parsed = null; }
  }
  if (!res.ok) {
    const { detail, code } = detailFrom(parsed, res.statusText || `Request failed (${res.status})`);
    throw new ApiError(kindForStatus(res.status), res.status, detail, code);
  }
  return parsed as T;
}
