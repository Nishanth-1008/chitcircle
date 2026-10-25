import { describe, expect, it, vi } from 'vitest';
import { request } from '@/lib/api/client';
import { ApiError, describeError } from '@/lib/api/errors';
import { api } from '@/lib/api/endpoints';
import { DEMO_CIRCLE_IDS, DEMO_CYCLE_IDS } from '@/lib/api/demo';

const live = { mode: 'live' as const, actor: { id: 'org-1', role: 'organizer' } };
const demo = { mode: 'demo' as const, actor: { id: 'demo-alex', role: 'member' } };

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('api client (live)', () => {
  it('calls the same-origin proxy and sends the dev identity headers for identification only', async () => {
    const f = mockFetch(200, { id: 'c1' });
    await api.getCircle(live, 'c 1');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/backend/circles/c%201');
    expect(init.headers['X-Actor-Id']).toBe('org-1');
    expect(init.method).toBe('GET');
    expect(init.cache).toBe('no-store');
  });
  it('maps 403 to a forbidden error (permission denied)', async () => {
    mockFetch(403, { code: 'FORBIDDEN', detail: 'only the circle organizer may perform this action' });
    const err = await api.getCircle(live, 'x').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe('forbidden');
    expect(err.code).toBe('FORBIDDEN');
    expect(describeError(err).title).toBe("You don't have access");
  });
  it('maps 404, 409 and 422 (string and array detail)', async () => {
    mockFetch(404, { code: 'NOT_FOUND', detail: 'cycle not found' });
    expect((await api.getCycle(live, 'x').catch((e) => e)).kind).toBe('not_found');
    mockFetch(409, { code: 'CONFLICT', detail: 'busy' });
    expect((await api.getCycle(live, 'x').catch((e) => e)).kind).toBe('conflict');
    mockFetch(422, { detail: [{ msg: 'field required', loc: ['body'] }] });
    const e = (await request<unknown>(live, '/circles', { method: 'POST', body: {} }).catch((x) => x)) as ApiError;
    expect(e.kind).toBe('validation');
    expect(e.detail).toBe('field required');
  });
  it('maps a failed fetch to a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const e = await api.health(live).catch((x) => x);
    expect(e.kind).toBe('network');
    expect(describeError(e).title).toMatch(/reach the server/i);
  });
  it('maps an AbortError to an aborted error and short-circuits an already-aborted signal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name: 'AbortError' })));
    expect((await api.health(live).catch((x) => x)).kind).toBe('aborted');
    const ac = new AbortController(); ac.abort();
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    expect((await api.health(live, ac.signal).catch((x) => x)).kind).toBe('aborted');
    expect(f).not.toHaveBeenCalled();
  });
  it('refuses to call the backend without an identity', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    const e = await api.health({ mode: 'live', actor: null }).catch((x) => x);
    expect(e.kind).toBe('unauthorized');
    expect(f).not.toHaveBeenCalled();
  });
  it('never exposes a webhook or write endpoint helper', () => {
    expect(Object.keys(api).sort()).toEqual(['getCircle', 'getCycle', 'getLedger', 'getReconciliation', 'getSettlement', 'health', 'listBids']);
  });
});

describe('api client (demo)', () => {
  it('serves fictional fixtures for read endpoints', async () => {
    const c = await api.getCircle(demo, DEMO_CIRCLE_IDS.weekend);
    expect(c.members).toHaveLength(10);
    const l = await api.getLedger(demo, DEMO_CYCLE_IDS.weekend);
    expect(l.some((e) => e.provider_ref?.startsWith('DEMO-'))).toBe(true);
  });
  it('rejects any write in demo mode', async () => {
    const e = (await request<unknown>(demo, '/circles', { method: 'POST', body: {} }).catch((x) => x)) as ApiError;
    expect(e.kind).toBe('unavailable');
  });
  it('returns not_found for unknown IDs', async () => {
    expect((await api.getCircle(demo, 'nope').catch((e) => e)).kind).toBe('not_found');
  });
  it('demo settlement figures are consistent with the documented model (fixtures, not frontend maths)', async () => {
    const s = (await api.getSettlement(demo, 'demo-settlement-weekend-4')).settlement;
    const net = Object.values(s.net_contributions).reduce((a, m) => a + m.minor, 0);
    expect(net).toBe(s.winner_payout.minor + s.commission.minor + s.rounding_remainder.minor);
  });
});
