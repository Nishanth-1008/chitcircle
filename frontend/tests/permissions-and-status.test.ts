import { describe, expect, it } from 'vitest';
import { canViewMemberSecurity, isOrganizer, roleIn } from '@/lib/permissions';
import { describeLedgerEvent, findSettlementId, matchesFilter } from '@/lib/ledger';
import { CYCLE_STATE_INFO, phaseOf, stateInfo } from '@/lib/status';
import { myObligation, settledCount } from '@/lib/derive';
import { dueLabel } from '@/lib/format';
import type { CircleView, CycleView, LedgerEventView } from '@/lib/types';

const circle: CircleView = {
  id: 'c', name: 'C', organizer_id: 'org', rulesets: [],
  members: [{ id: 'm1', name: 'A', position: 1, has_won: false, security_status: 'NONE' }],
};

describe('role gating is derived from server data, never from the header role', () => {
  it('organizer comes from circle.organizer_id', () => {
    expect(isOrganizer(circle, { id: 'org', role: 'member' })).toBe(true);
    expect(isOrganizer(circle, { id: 'm1', role: 'organizer' })).toBe(false); // forged role header is ignored
    expect(roleIn(circle, { id: 'm1', role: 'organizer' })).toBe('member');
    expect(roleIn(circle, { id: 'zzz', role: 'organizer' })).toBe('none');
    expect(roleIn(circle, null)).toBe('none');
  });
  it('member security status is only shown to organizers (UI nicety; the API still decides access)', () => {
    expect(canViewMemberSecurity('organizer')).toBe(true);
    expect(canViewMemberSecurity('member')).toBe(false);
    expect(canViewMemberSecurity('none')).toBe(false);
  });
});

describe('status mapping never overstates what has happened', () => {
  it('covers every backend cycle state', () => {
    expect(Object.keys(CYCLE_STATE_INFO)).toHaveLength(16);
  });
  it('approved / payout requested are not "paid"', () => {
    expect(stateInfo('APPROVED').hint).toMatch(/not been requested or confirmed/i);
    expect(stateInfo('PAYOUT_PENDING').hint).toMatch(/not confirmed/i);
    expect(stateInfo('PAYOUT_SUBMITTED').settlementLabel).toBe('Payout submitted');
    expect(stateInfo('PAYOUT_CONFIRMED').settlementLabel).toBe('Provider confirmed');
    expect(stateInfo('PAYOUT_CONFIRMED').tone).not.toBe('success');
    expect(stateInfo('FINALIZED').tone).toBe('success');
  });
  it('exception states use the prior state for the stepper', () => {
    expect(phaseOf('ON_HOLD', 'AWAITING_APPROVAL')).toBe(3);
    expect(phaseOf('FAILED', null)).toBe(0);
  });
  it('unknown states degrade gracefully', () => {
    expect(stateInfo('SOMETHING_NEW').label).toBe('Something new');
  });
});

describe('ledger presentation', () => {
  const ev = (type: string, extra: Partial<LedgerEventView> = {}): LedgerEventView => ({
    id: type, type, member_id: null, amount: 1, currency: 'INR', timestamp: '2026-10-01T00:00:00Z', actor: 'x',
    ruleset_version: 1, settlement_id: null, provider_ref: null, reverses: null, reason: null, journal: null, ...extra });
  it('a scheduled contribution is not a completed payment', () => {
    const d = describeLedgerEvent({ type: 'CONTRIBUTION_DUE', reverses: null });
    expect(d.pending).toBe(true);
    expect(d.direction).toBe('none');
    expect(d.status).toMatch(/not paid/i);
    expect(matchesFilter(ev('CONTRIBUTION_DUE'), 'pending')).toBe(true);
    expect(matchesFilter(ev('CONTRIBUTION_DUE'), 'incoming')).toBe(false);
  });
  it('only provider-confirmed payments are incoming; a requested payout is pending, not outgoing', () => {
    expect(matchesFilter(ev('PAYMENT_CONFIRMED'), 'incoming')).toBe(true);
    expect(matchesFilter(ev('PAYOUT_REQUESTED'), 'outgoing')).toBe(false);
    expect(matchesFilter(ev('PAYOUT_REQUESTED'), 'pending')).toBe(true);
    expect(matchesFilter(ev('PAYOUT_CONFIRMED'), 'outgoing')).toBe(true);
  });
  it('labels reversals', () => {
    expect(describeLedgerEvent({ type: 'PAYMENT_CONFIRMED', reverses: 'e1' }).title).toMatch(/^Reversal/);
  });
  it('finds the settlement id from ledger events', () => {
    expect(findSettlementId([ev('A'), ev('DIVIDEND_CREDITED', { settlement_id: 's1' })])).toBe('s1');
    expect(findSettlementId([ev('A')])).toBeNull();
    expect(findSettlementId(undefined)).toBeNull();
  });
});

describe('derive helpers read server fields only', () => {
  const cycle = { obligations: [
    { member_id: 'm1', gross_due: 10, dividend_credit: 0, net_payable: 10, confirmed_paid: 10, outstanding: 0 },
    { member_id: 'm2', gross_due: 10, dividend_credit: 0, net_payable: 10, confirmed_paid: 0, outstanding: 10 },
  ] } as unknown as CycleView;
  it('finds my obligation and counts settled members', () => {
    expect(myObligation(cycle, { id: 'm2', role: 'member' })?.outstanding).toBe(10);
    expect(myObligation(cycle, null)).toBeUndefined();
    expect(settledCount(cycle)).toBe(1);
  });
  it('due labels', () => {
    const now = Date.parse('2026-10-25T00:00:00Z');
    expect(dueLabel('2026-10-28T00:00:00Z', now)).toBe('3 days left');
    expect(dueLabel('2026-10-25T00:00:00Z', now)).toBe('Due today');
    expect(dueLabel('2026-10-23T00:00:00Z', now)).toBe('2 days overdue');
  });
});
