import { API_BASE } from '../config';
import { ApiError, detailFrom, kindForStatus } from './errors';

export interface ApiContext {
  token: string | null;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Sent as application/x-www-form-urlencoded instead of JSON (OAuth2 password login). */
  form?: Record<string, string>;
  query?: Record<string, string | number | undefined | null>;
  signal?: AbortSignal;
  /** Allow calls without a session (health, config, login, register). */
  anonymous?: boolean;
}

export const UNAUTHORIZED_EVENT = 'chitcircle:unauthorized';

function withQuery(path: string, query?: RequestOptions['query']): string {
  if (!query) return path;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  const s = qs.toString();
  return s ? `${path}${path.includes('?') ? '&' : '?'}${s}` : path;
}

/**
 * One typed entry point for every backend call. The browser only talks to the same-origin `/api/backend/*`
 * proxy. State-changing calls carry a fresh Idempotency-Key so a retried request is replayed, not repeated.
 */
export async function request<T>(ctx: ApiContext, path: string, opts: RequestOptions = {}): Promise<T> {
  if (opts.signal?.aborted) throw new ApiError('aborted', 0, 'Request cancelled');
  if (!ctx.token && !opts.anonymous) throw new ApiError('unauthorized', 401, 'Sign in to continue.');

  const method = opts.method ?? 'GET';
  const mutating = method !== 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (opts.form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    body = new URLSearchParams(opts.form).toString();
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  if (mutating) headers['Idempotency-Key'] = crypto.randomUUID();
  if (ctx.token) headers.Authorization = `Bearer ${ctx.token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${withQuery(path, opts.query)}`, {
      method, signal: opts.signal, cache: 'no-store', headers, body,
    });
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') throw new ApiError('aborted', 0, 'Request cancelled');
    throw new ApiError('network', 0, 'Network request failed');
  }

  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try { parsed = JSON.parse(text); } catch { parsed = null; }
  }
  if (!res.ok) {
    if (res.status === 401 && ctx.token && typeof window !== 'undefined') {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    const fallback = res.status >= 500 && !parsed ? 'The API is not responding. Is the backend running?' : res.statusText || `Request failed (${res.status})`;
    const { detail, code, extra } = detailFrom(parsed, fallback);
    throw new ApiError(kindForStatus(res.status), res.status, detail, code, extra);
  }
  return parsed as T;
}
