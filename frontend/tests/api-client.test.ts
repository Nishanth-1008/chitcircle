import { describe, expect, it, vi } from 'vitest';
import { request } from '@/lib/api/client';
import { ApiError, describeError } from '@/lib/api/errors';
import { api } from '@/lib/api/endpoints';

const actor = { id: 'org-1', role: 'organizer' };
const ctx = { actor };

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('api client', () => {
  it('calls the same-origin proxy and sends the dev identity headers for identification only', async () => {
    const f = mockFetch(200, { id: 'c1' });
    await api.getCircle(ctx, 'c 1');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/backend/circles/c%201');
    expect(init.headers['X-Actor-Id']).toBe('org-1');
    expect(init.method).toBe('GET');
    expect(init.cache).toBe('no-store');
  });
  it('maps 403 to a forbidden error (permission denied)', async () => {
    mockFetch(403, { code: 'FORBIDDEN', detail: 'only the circle organizer may perform this action' });
    const err = await api.getCircle(ctx, 'x').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe('forbidden');
    expect(err.code).toBe('FORBIDDEN');
    expect(describeError(err).title).toBe("You don't have access");
  });
  it('maps 404, 409 and 422 (string and array detail)', async () => {
    mockFetch(404, { code: 'NOT_FOUND', detail: 'cycle not found' });
    expect((await api.getCycle(ctx, 'x').catch((e) => e)).kind).toBe('not_found');
    mockFetch(409, { code: 'CONFLICT', detail: 'busy' });
    expect((await api.getCycle(ctx, 'x').catch((e) => e)).kind).toBe('conflict');
    mockFetch(422, { detail: [{ msg: 'field required', loc: ['body'] }] });
    const e = (await request<unknown>(ctx, '/circles', { method: 'POST', body: {} }).catch((x) => x)) as ApiError;
    expect(e.kind).toBe('validation');
    expect(e.detail).toBe('field required');
  });
  it('maps a failed fetch to a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const e = await api.health(ctx).catch((x) => x);
    expect(e.kind).toBe('network');
    expect(describeError(e).title).toMatch(/reach the server/i);
  });
  it('maps an AbortError to an aborted error and short-circuits an already-aborted signal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name: 'AbortError' })));
    expect((await api.health(ctx).catch((x) => x)).kind).toBe('aborted');
    const ac = new AbortController(); ac.abort();
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    expect((await api.health(ctx, ac.signal).catch((x) => x)).kind).toBe('aborted');
    expect(f).not.toHaveBeenCalled();
  });
  it('refuses to call the backend without an identity', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    const e = await api.health({ actor: null }).catch((x) => x);
    expect(e.kind).toBe('unauthorized');
    expect(f).not.toHaveBeenCalled();
  });
});
