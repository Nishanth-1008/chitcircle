export type ApiErrorKind =
  | 'network' | 'unauthorized' | 'forbidden' | 'not_found' | 'conflict' | 'validation' | 'server' | 'unavailable' | 'aborted';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly code?: string;
  readonly detail: string;

  constructor(kind: ApiErrorKind, status: number, detail: string, code?: string) {
    super(detail);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 400 || status === 422) return 'validation';
  if (status === 501 || status === 503) return 'unavailable';
  return 'server';
}

/** FastAPI returns {code, detail:string} from our handlers and {detail:[{msg,loc}]} for request validation. */
export function detailFrom(body: unknown, fallback: string): { detail: string; code?: string } {
  if (body && typeof body === 'object') {
    const b = body as { detail?: unknown; code?: unknown };
    const code = typeof b.code === 'string' ? b.code : undefined;
    if (typeof b.detail === 'string') return { detail: b.detail, code };
    if (Array.isArray(b.detail)) {
      const msgs = b.detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean);
      if (msgs.length) return { detail: msgs.join('; '), code };
    }
  }
  return { detail: fallback };
}

export function describeError(err: unknown): { title: string; message: string } {
  if (err instanceof ApiError) {
    switch (err.kind) {
      case 'network':
        return { title: "Can't reach the server", message: 'Check your connection and that the ChitCircle API is running, then try again.' };
      case 'unauthorized':
        return { title: 'Sign in required', message: err.detail || 'Your session is missing or has expired.' };
      case 'forbidden':
        return { title: "You don't have access", message: err.detail || 'The server did not allow this account to view this.' };
      case 'not_found':
        return { title: 'Not found', message: err.detail || "We couldn't find that record. Check the ID and try again." };
      case 'unavailable':
        return { title: 'Not available yet', message: err.detail || 'This part of the backend is not connected.' };
      case 'conflict':
      case 'validation':
        return { title: 'The server rejected this', message: err.detail };
      default:
        return { title: 'Something went wrong', message: err.detail || 'The server returned an unexpected error. Try again in a moment.' };
    }
  }
  if (err instanceof Error && err.message) return { title: 'Something went wrong', message: err.message };
  return { title: 'Something went wrong', message: 'An unexpected error occurred.' };
}
