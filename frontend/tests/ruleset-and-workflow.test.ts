import { describe, expect, it } from 'vitest';
import { buildRuleset, describeRules, percentToRate, rateToPercent, type RulesForm } from '@/lib/ruleset';
import type { CycleSummary, MyCircle, RulesetData } from '@/lib/types';
import { circleAttention, paymentOpen } from '@/lib/workflow';

const form: RulesForm = {
  currency: 'INR', payoutMode: 'SEALED_BID_AUCTION', chitValueMinor: 10_000_000, memberCount: 20,
  commissionPercent: '5', maxDiscountPercent: '40', minIncrementMinor: 0, tieBreak: 'EARLIEST_BID',
  noBidFallback: 'HOLD', dividendAllocation: 'ALL_MEMBERS', gracePeriodDays: 5, requiredApprovals: 1,
  requireSecurity: false, requireFullCollection: true,
};

describe('ruleset builder', () => {
  it('converts percentages to exact decimal rate strings', () => {
    expect(percentToRate('5')).toBe('0.05');
    expect(percentToRate('12.5')).toBe('0.125');
    expect(percentToRate('40')).toBe('0.4');
    expect(percentToRate('0')).toBe('0');
    expect(percentToRate('100')).toBe('1');
    expect(percentToRate('101')).toBeNull();
    expect(percentToRate('abc')).toBeNull();
    expect(rateToPercent('0.05')).toBe('5%');
    expect(rateToPercent('0.125')).toBe('12.5%');
    expect(rateToPercent('1')).toBe('100%');
  });
  it('builds the engine ruleset with integer money and explicit rounding policy', () => {
    const r = buildRuleset(form, new Date('2026-11-09T00:00:00Z'));
    expect(r).toMatchObject({
      currency: 'INR', total_chit_value: 10_000_000, member_count: 20, payout_mode: 'SEALED_BID_AUCTION',
      commission: { base: 'PERCENT_OF_CHIT_VALUE', rate: '0.05', rounding: 'HALF_UP' },
      auction: { max_discount_rate: '0.4', tie_break: 'EARLIEST_BID', no_bid_fallback: 'HOLD', increment: 0 },
      rounding: { contribution_remainder: 'REJECT', remainder_destination: 'ORGANIZER' },
      effective_date: '2026-11-09', status: 'ACTIVE',
    });
    expect(buildRuleset({ ...form, payoutMode: 'FIXED_ROTATION' }).auction).toBeNull();
  });
  it('describes the rules in plain language', () => {
    const lines = describeRules(buildRuleset(form) as unknown as RulesetData);
    expect(lines[0]).toBe('The pot is ₹1,00,000, shared equally by 20 members each round.');
    expect(lines.join(' ')).toMatch(/commission is 5% of the pot/);
    expect(lines.join(' ')).toMatch(/capped at 40% of the pot/);
  });
});

const cycle = (over: Partial<CycleSummary>): CycleSummary => ({
  id: 'cy', number: 1, state: 'COLLECTIONS_IN_PROGRESS', prior_state: null, due_date: '2026-11-20T12:00:00Z',
  ruleset_version: 1, payout_method: null, winner_member_id: null, discount: null, settlement_id: null,
  settlement_status: null, obligations_total: 4, obligations_settled: 0, outstanding_total: 0,
  my_outstanding: 100_000, my_net_payable: 100_000, ...over,
});

describe('payment timing', () => {
  it('auction installments are payable only after settlement', () => {
    expect(paymentOpen('SEALED_BID_AUCTION', cycle({}))).toBe(false);
    expect(paymentOpen('SEALED_BID_AUCTION', cycle({ state: 'AWAITING_APPROVAL', settlement_id: 's' }))).toBe(true);
    expect(paymentOpen('FIXED_ROTATION', cycle({}))).toBe(true);
    expect(paymentOpen('FIXED_ROTATION', cycle({ state: 'DRAFT' }))).toBe(false);
    expect(paymentOpen('FIXED_ROTATION', cycle({ state: 'FINALIZED' }))).toBe(false);
  });
});

describe('needs-attention items', () => {
  const circle = (over: Partial<MyCircle>): MyCircle => ({
    id: 'c', name: 'Family', organizer_id: 'o', my_role: 'organizer', my_member_id: null, currency: 'INR',
    total_chit_value: 400_000, member_count: 4, won_count: 0, payout_mode: 'SEALED_BID_AUCTION', pending_actions: 0,
    current_cycle: cycle({}), ...over,
  });
  it('tells the organizer what to do next', () => {
    expect(circleAttention(circle({ current_cycle: null })).map((a) => a.title)).toEqual(['Start the first round']);
    expect(circleAttention(circle({})).map((a) => a.title)).toEqual(['Open the auction']);
    expect(circleAttention(circle({ current_cycle: cycle({ state: 'AWAITING_APPROVAL', settlement_id: 's1' }) }))[0].href)
      .toBe('/app/settlements/s1');
    expect(circleAttention(circle({ pending_actions: 2 }))[0].title).toBe('2 proposed actions to review');
  });
  it('asks a member to pay only when the installment is final', () => {
    const member = { my_role: 'member' as const, my_member_id: 'm1' };
    expect(circleAttention(circle({ ...member }))).toEqual([]);
    const settled = circleAttention(circle({ ...member, current_cycle: cycle({ state: 'AWAITING_APPROVAL', settlement_id: 's' }) }));
    expect(settled.map((a) => a.title)).toEqual(['Your contribution is due']);
    expect(circleAttention(circle({ ...member, current_cycle: cycle({ state: 'AUCTION_OPEN' }) }))[0].title)
      .toBe('Auction is open — place your bid');
  });
});
