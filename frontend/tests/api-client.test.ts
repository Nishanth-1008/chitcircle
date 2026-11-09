import { describe, expect, it, vi } from 'vitest';
import { request, UNAUTHORIZED_EVENT } from '@/lib/api/client';
import { ApiError, describeError } from '@/lib/api/errors';
import { api } from '@/lib/api/endpoints';

const ctx = { token: 'jwt-abc' };

function mockFetch(status: number, body: unknown) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fn = vi.fn(async (_url: string, _init?: any) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('api client', () => {
  it('calls the same-origin proxy with the bearer token and no idempotency key on reads', async () => {
    const f = mockFetch(200, { id: 'c1' });
    await api.getCircle(ctx, 'c 1');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/backend/circles/c%201');
    expect(init.headers.Authorization).toBe('Bearer jwt-abc');
    expect(init.headers['Idempotency-Key']).toBeUndefined();
    expect(init.method).toBe('GET');
    expect(init.cache).toBe('no-store');
  });
  it('sends a fresh Idempotency-Key and JSON body on every state-changing call', async () => {
    const f = mockFetch(200, { bid_id: 'b', accepted: true, reasons: [] });
    await api.submitBid(ctx, 'cy', 'm1', 1_200_000);
    await api.submitBid(ctx, 'cy', 'm1', 1_200_000);
    const [, a] = f.mock.calls[0];
    const [, b] = f.mock.calls[1];
    expect(a.method).toBe('POST');
    expect(JSON.parse(a.body)).toEqual({ member_id: 'm1', discount: 1_200_000 });
    expect(a.headers['Idempotency-Key']).toMatch(/[0-9a-f-]{36}/);
    expect(a.headers['Idempotency-Key']).not.toBe(b.headers['Idempotency-Key']);
  });
  it('logs in with an OAuth2 form body and no session', async () => {
    const f = mockFetch(200, { access_token: 't', expires_in: 3600, user: { id: 'u' } });
    await api.login('a@b.co', 'secret123');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/backend/auth/login');
    expect(init.headers['Content-Type']).toBe('application/x-www-form-urlencoded');
    expect(init.body).toBe('username=a%40b.co&password=secret123');
    expect(init.headers.Authorization).toBeUndefined();
  });
  it('encodes query parameters and skips empty ones', async () => {
    const f = mockFetch(200, { items: [], next_cursor: null, has_more: false });
    await api.circleLedger(ctx, 'c1', { cursor: 'a|b', limit: 50, cycle_id: undefined });
    expect(f.mock.calls[0][0]).toBe('/api/backend/circles/c1/ledger?cursor=a%7Cb&limit=50');
  });
  it('maps problem details (403/404/409/422) to typed errors with extra fields', async () => {
    mockFetch(403, { code: 'FORBIDDEN', detail: 'only the circle organizer may perform this action' });
    const err = await api.getCircle(ctx, 'x').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe('forbidden');
    expect(err.detail).toBe('Only the circle organizer may perform this action');
    expect(describeError(err).title).toBe("You don't have access");
    mockFetch(409, { code: 'COLLECTIONS_INCOMPLETE', detail: 'collections are incomplete', members_outstanding: ['m2'] });
    const c = await api.executePayout(ctx, 's').catch((e) => e);
    expect(c.kind).toBe('conflict');
    expect(c.extra.members_outstanding).toEqual(['m2']);
    mockFetch(422, { detail: [{ msg: 'field required', loc: ['body', 'name'] }] });
    const v = (await request<unknown>(ctx, '/circles', { method: 'POST', body: {} }).catch((x) => x)) as ApiError;
    expect(v.kind).toBe('validation');
    expect(v.detail).toBe('name: field required');
  });
  it('signals the session to sign out on a 401', async () => {
    mockFetch(401, { detail: 'Could not validate credentials' });
    const onUnauthorized = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    await api.myCircles(ctx).catch(() => undefined);
    window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
  it('maps a failed fetch to a network error and an aborted signal to aborted', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    expect((await api.health(ctx).catch((x) => x)).kind).toBe('network');
    const ac = new AbortController(); ac.abort();
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    expect((await api.health(ctx, ac.signal).catch((x) => x)).kind).toBe('aborted');
    expect(f).not.toHaveBeenCalled();
  });
  it('refuses authenticated calls without a session but allows public ones', async () => {
    const f = mockFetch(200, { status: 'ok' });
    expect((await api.myCircles({ token: null }).catch((x) => x)).kind).toBe('unauthorized');
    expect(f).not.toHaveBeenCalled();
    await api.health({ token: null });
    expect(f).toHaveBeenCalledTimes(1);
  });
});
