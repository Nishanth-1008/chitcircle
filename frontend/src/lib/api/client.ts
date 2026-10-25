import { API_BASE } from '../config';
import type { Actor } from '../permissions';
import { demoRequest } from './demo';
import { ApiError, detailFrom, kindForStatus } from './errors';

export type DataMode = 'demo' | 'live';

export interface ApiContext {
  mode: DataMode;
  actor: Actor | null;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT';
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * One typed entry point for every backend call.
 * - Live: same-origin /api/backend/* (proxied by Next to FastAPI; no secrets in the browser).
 * - Demo: fixtures that mimic the read endpoints and are always labelled as demo data in the UI.
 * The X-Actor-* headers are the backend's development auth stub. They are sent for identification only and are
 * NEVER used by this client as proof of permission.
 */
export async function request<T>(ctx: ApiContext, path: string, opts: RequestOptions = {}): Promise<T> {
  if (opts.signal?.aborted) throw new ApiError('aborted', 0, 'Request cancelled');
  if (ctx.mode === 'demo') return demoRequest<T>(path, opts);
  if (!ctx.actor) throw new ApiError('unauthorized', 401, 'Sign in to continue.');

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: opts.method ?? 'GET',
      signal: opts.signal,
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
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
