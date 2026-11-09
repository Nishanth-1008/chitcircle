import { describe, expect, it } from 'vitest';
import { dueLabel } from '@/lib/format';
import { describeLedgerEvent, findSettlementId, matchesFilter } from '@/lib/ledger';
import { reconcileLabel } from '@/lib/reconcile';
import { fromToken, parseStored } from '@/lib/session';
import { CYCLE_STATE_INFO, phaseOf, reasonLabel, stateInfo } from '@/lib/status';
import type { LedgerEventView } from '@/lib/types';

describe('status mapping never overstates what has happened', () => {
  it('covers every backend cycle state', () => {
    expect(Object.keys(CYCLE_STATE_INFO)).toHaveLength(16);
  });
  it('approved / payout requested are not "paid"', () => {
    expect(stateInfo('APPROVED').hint).toMatch(/not been requested or confirmed/i);
    expect(stateInfo('PAYOUT_PENDING').hint).toMatch(/not confirmed/i);
    expect(stateInfo('PAYOUT_CONFIRMED').tone).not.toBe('success');
    expect(stateInfo('FINALIZED').tone).toBe('success');
  });
  it('exception states use the prior state for the stepper', () => {
    expect(phaseOf('ON_HOLD', 'AWAITING_APPROVAL')).toBe(3);
    expect(phaseOf('FAILED', null)).toBe(0);
  });
  it('unknown states and reasons degrade gracefully', () => {
    expect(stateInfo('SOMETHING_NEW').label).toBe('Something new');
    expect(reasonLabel('DISCOUNT_ABOVE_CAP')).toBe('Above the maximum discount allowed.');
    expect(reasonLabel('NEW_REASON')).toBe('New reason');
    expect(reconcileLabel('UNDERPAID')).toBe('Paid less than the amount due');
  });
});

describe('ledger presentation', () => {
  const ev = (type: string, extra: Partial<LedgerEventView> = {}): LedgerEventView => ({
    id: type, type, member_id: null, amount: 1, currency: 'INR', timestamp: '2026-10-01T00:00:00Z', actor: 'x',
    ruleset_version: 1, settlement_id: null, provider_ref: null, reverses: null, reason: null, journal: null, ...extra });
  it('a scheduled contribution is not a completed payment', () => {
    const d = describeLedgerEvent({ type: 'CONTRIBUTION_DUE', reverses: null });
    expect(d.pending).toBe(true);
    expect(d.status).toMatch(/not paid/i);
    expect(matchesFilter(ev('CONTRIBUTION_DUE'), 'pending')).toBe(true);
    expect(matchesFilter(ev('CONTRIBUTION_DUE'), 'incoming')).toBe(false);
  });
  it('only provider-confirmed payments are incoming; a requested payout is pending', () => {
    expect(matchesFilter(ev('PAYMENT_CONFIRMED'), 'incoming')).toBe(true);
    expect(matchesFilter(ev('PAYOUT_REQUESTED'), 'outgoing')).toBe(false);
    expect(matchesFilter(ev('PAYOUT_REQUESTED'), 'pending')).toBe(true);
    expect(matchesFilter(ev('PAYOUT_CONFIRMED'), 'outgoing')).toBe(true);
  });
  it('labels reversals and finds settlement ids', () => {
    expect(describeLedgerEvent({ type: 'PAYMENT_CONFIRMED', reverses: 'e1' }).title).toMatch(/^Reversal/);
    expect(findSettlementId([ev('A'), ev('DIVIDEND_CREDITED', { settlement_id: 's1' })])).toBe('s1');
    expect(findSettlementId(undefined)).toBeNull();
  });
  it('due labels', () => {
    const now = Date.parse('2026-10-25T00:00:00Z');
    expect(dueLabel('2026-10-28T00:00:00Z', now)).toBe('3 days left');
    expect(dueLabel('2026-10-25T00:00:00Z', now)).toBe('Due today');
    expect(dueLabel('2026-10-23T00:00:00Z', now)).toBe('2 days overdue');
  });
});

describe('stored session', () => {
  const user = { id: 'u1', email: 'a@b.co', name: 'A', role: 'member', payout_email: null, payout_email_verified: false };
  it('round-trips a token response and rejects expired or malformed sessions', () => {
    const now = 1_000_000;
    const s = fromToken({ access_token: 't', token_type: 'bearer', user_id: 'u1', role: 'member', expires_in: 60, user }, now);
    expect(s.expiresAt).toBe(now + 60_000);
    expect(parseStored(JSON.stringify(s), now)).toEqual(s);
    expect(parseStored(JSON.stringify(s), now + 60_001)).toBeNull();
    expect(parseStored('{"token":1}', now)).toBeNull();
    expect(parseStored('not json', now)).toBeNull();
    expect(parseStored(null, now)).toBeNull();
  });
});
