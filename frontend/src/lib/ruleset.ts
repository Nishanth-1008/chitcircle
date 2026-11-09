/**
 * Circle rules: building the ruleset document from the setup form, and describing a stored ruleset in plain words.
 * No money is calculated here; amounts the form collects are converted to minor units and the engine does the rest.
 */
import { safeFormatMinor } from './money';
import type { PayoutMode, RulesetData } from './types';

export interface RulesForm {
  currency: string;
  payoutMode: PayoutMode;
  chitValueMinor: number;
  memberCount: number;
  commissionPercent: string;
  maxDiscountPercent: string;
  minIncrementMinor: number;
  tieBreak: 'EARLIEST_BID' | 'LOWEST_POSITION' | 'SEEDED_RANDOM';
  noBidFallback: 'HOLD' | 'FIXED_ROTATION' | 'LOTTERY';
  dividendAllocation: 'ALL_MEMBERS' | 'ELIGIBLE_MEMBERS';
  gracePeriodDays: number;
  requiredApprovals: number;
  requireSecurity: boolean;
  requireFullCollection: boolean;
}

export const PAYOUT_MODES: { id: PayoutMode; title: string; tradition: string; body: string }[] = [
  { id: 'SEALED_BID_AUCTION', title: 'Sealed-bid auction', tradition: 'Chit fund',
    body: 'Members bid a discount privately. The highest discount wins the pot; the discount (minus commission) is shared back as dividends.' },
  { id: 'OPEN_BID_AUCTION', title: 'Open auction', tradition: 'Chit fund',
    body: 'Bids are visible and must beat the current best. Same settlement math as the sealed auction.' },
  { id: 'FIXED_ROTATION', title: 'Fixed rotation', tradition: 'Tanda · ROSCA · Susu · Committee',
    body: 'Members receive the pot in seat order. No bidding, no dividends.' },
  { id: 'LOTTERY', title: 'Auditable lottery', tradition: 'Lucky draw',
    body: 'A committed random draw picks the recipient from members who have not won yet.' },
];

export const isAuction = (mode: string) => mode === 'SEALED_BID_AUCTION' || mode === 'OPEN_BID_AUCTION';

/** "5" or "5.25" → "0.05" / "0.0525", exactly, without floating-point arithmetic. */
export function percentToRate(percent: string): string | null {
  const m = /^(\d{1,3})(?:\.(\d{1,4}))?$/.exec(percent.trim());
  if (!m) return null;
  const whole = Number(m[1]);
  if (whole > 100 || (whole === 100 && Number(m[2] ?? 0) > 0)) return null;
  const digits = `${m[1].padStart(3, '0')}${(m[2] ?? '').padEnd(4, '0')}`;      // 3 int + 4 frac digits
  const rate = `${digits.slice(0, 1)}.${digits.slice(1)}`.replace(/0+$/, '').replace(/\.$/, '');
  return rate === '' ? '0' : rate;
}

export function rateToPercent(rate: string | null | undefined): string {
  if (!rate) return '0%';
  const m = /^(\d+)(?:\.(\d+))?$/.exec(rate);
  if (!m) return `${rate}`;
  const frac = (m[2] ?? '').padEnd(2, '0');
  const whole = String(Number(`${m[1]}${frac.slice(0, 2)}`));
  const rest = frac.slice(2).replace(/0+$/, '');
  return `${whole}${rest ? `.${rest}` : ''}%`;
}

export function buildRuleset(f: RulesForm, today = new Date()): Record<string, unknown> {
  const auction = isAuction(f.payoutMode);
  return {
    currency: f.currency,
    total_chit_value: f.chitValueMinor,
    member_count: f.memberCount,
    payout_mode: f.payoutMode,
    commission: { base: 'PERCENT_OF_CHIT_VALUE', rate: percentToRate(f.commissionPercent) ?? '0', rounding: 'HALF_UP' },
    dividend: { allocation: f.dividendAllocation },
    auction: auction ? {
      max_discount_rate: percentToRate(f.maxDiscountPercent) ?? '0.3',
      min_discount: 0,
      increment: f.minIncrementMinor,
      tie_break: f.tieBreak,
      no_bid_fallback: f.noBidFallback,
    } : null,
    grace_period_days: f.gracePeriodDays,
    rounding: { contribution_remainder: 'REJECT', remainder_destination: 'ORGANIZER' },
    required_approvals: f.requiredApprovals,
    require_security: f.requireSecurity,
    require_full_collection_before_payout: f.requireFullCollection,
    one_win_per_member: true,
    jurisdiction_profile: f.currency === 'INR' ? 'IN-SANDBOX' : 'GLOBAL-SANDBOX',
    effective_date: today.toISOString().slice(0, 10),
    status: 'ACTIVE',
  };
}

const TIE_BREAK: Record<string, string> = {
  EARLIEST_BID: 'the earliest bid wins a tie',
  LOWEST_POSITION: 'the lower seat number wins a tie',
  SEEDED_RANDOM: 'ties are settled by a committed random draw',
};
const FALLBACK: Record<string, string> = {
  HOLD: 'the round is put on hold for the organizer',
  FIXED_ROTATION: 'the next member in seat order receives the pot',
  LOTTERY: 'a committed lottery picks the recipient',
};

export const payoutModeTitle = (mode: string) => PAYOUT_MODES.find((m) => m.id === mode)?.title ?? mode;

/** Plain-language rules summary members can read before they trust the circle. */
export function describeRules(r: RulesetData): string[] {
  const pot = safeFormatMinor(r.total_chit_value, r.currency);
  const out = [
    `The pot is ${pot}, shared equally by ${r.member_count} members each round.`,
    `${payoutModeTitle(r.payout_mode)}: ${PAYOUT_MODES.find((m) => m.id === r.payout_mode)?.body ?? ''}`,
  ];
  if (r.commission.base === 'FIXED_AMOUNT') {
    out.push(`The organizer's commission is a fixed ${safeFormatMinor(r.commission.fixed_amount, r.currency)} per round.`);
  } else {
    const of = r.commission.base === 'PERCENT_OF_DISCOUNT' ? 'the winning discount' : 'the pot';
    out.push(`The organizer's commission is ${rateToPercent(r.commission.rate)} of ${of}.`);
  }
  if (r.auction && isAuction(r.payout_mode)) {
    out.push(`Discounts are capped at ${rateToPercent(r.auction.max_discount_rate)} of the pot`
      + (r.auction.increment ? `, in steps of ${safeFormatMinor(r.auction.increment, r.currency)}` : '') + '.');
    out.push(`If bids tie, ${TIE_BREAK[r.auction.tie_break] ?? r.auction.tie_break}. With no bids, ${FALLBACK[r.auction.no_bid_fallback] ?? r.auction.no_bid_fallback}.`);
    out.push(r.dividend.allocation === 'ALL_MEMBERS'
      ? 'Dividends are shared by every member.'
      : 'Dividends go to members who are not in arrears past the grace period.');
  }
  out.push(`Contributions have a ${r.grace_period_days}-day grace period; after that a member in arrears cannot bid.`);
  out.push(r.one_win_per_member ? 'Each member receives the pot exactly once.' : 'Members may receive the pot more than once.');
  out.push(`${r.required_approvals} approval${r.required_approvals === 1 ? '' : 's'} required before a payout; the recipient can never approve their own.`);
  if (r.require_security) out.push('The winner must have verified security (guarantor or collateral) before the payout is released.');
  if (r.require_full_collection_before_payout) out.push('Every contribution must be confirmed before the pot is paid out.');
  return out;
}
