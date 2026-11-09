export type ApiErrorKind =
  | 'network' | 'unauthorized' | 'forbidden' | 'not_found' | 'conflict' | 'validation' | 'rate_limited'
  | 'server' | 'unavailable' | 'aborted';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly code?: string;
  readonly detail: string;
  /** Extra fields from an RFC 9457 problem body (e.g. `failures`, `members_outstanding`). */
  readonly extra: Record<string, unknown>;

  constructor(kind: ApiErrorKind, status: number, detail: string, code?: string, extra: Record<string, unknown> = {}) {
    super(detail);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.extra = extra;
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 429) return 'rate_limited';
  if (status === 400 || status === 422 || status === 428) return 'validation';
  if (status === 501 || status === 502 || status === 503) return 'unavailable';
  return 'server';
}

/** Problem details carry `{detail, code}`; FastAPI request validation carries `{detail: [{msg, loc}]}`. */
export function detailFrom(body: unknown, fallback: string): { detail: string; code?: string; extra: Record<string, unknown> } {
  if (body && typeof body === 'object') {
    const { detail, code, ...rest } = body as { detail?: unknown; code?: unknown } & Record<string, unknown>;
    const c = typeof code === 'string' ? code : undefined;
    if (typeof detail === 'string') return { detail: sentence(detail), code: c, extra: rest };
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => {
          if (!d || typeof d !== 'object') return '';
          const { msg, loc } = d as { msg?: unknown; loc?: unknown };
          const field = Array.isArray(loc) ? loc.filter((p) => p !== 'body').join('.') : '';
          return `${field ? `${field}: ` : ''}${String(msg ?? '')}`;
        })
        .filter(Boolean);
      if (msgs.length) return { detail: msgs.join('; '), code: c, extra: rest };
    }
  }
  return { detail: fallback, extra: {} };
}

const sentence = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export function describeError(err: unknown): { title: string; message: string } {
  if (err instanceof ApiError) {
    switch (err.kind) {
      case 'network':
        return { title: "Can't reach the server", message: 'Check that the ChitCircle API is running, then try again.' };
      case 'unauthorized':
        return { title: 'Sign in required', message: err.detail || 'Your session has expired. Sign in again.' };
      case 'forbidden':
        return { title: "You don't have access", message: err.detail };
      case 'not_found':
        return { title: 'Not found', message: err.detail || "We couldn't find that record." };
      case 'rate_limited':
        return { title: 'Slow down a little', message: 'Too many requests. Wait a few seconds and try again.' };
      case 'unavailable':
        return { title: 'Not available', message: err.detail || 'This part of the backend is not connected.' };
      case 'conflict':
      case 'validation':
        return { title: 'The server rejected this', message: err.detail };
      default:
        return { title: 'Something went wrong', message: err.detail || 'The server returned an unexpected error.' };
    }
  }
  if (err instanceof Error && err.message) return { title: 'Something went wrong', message: err.message };
  return { title: 'Something went wrong', message: 'An unexpected error occurred.' };
}

export const errorMessage = (err: unknown) => describeError(err).message;
