/**
 * Fictional demo fixtures that mimic the backend's READ endpoints.
 * Everything here is invented sample data (including names, IDs and provider references) used for layout and
 * interaction testing. The UI labels it "Demo mode - no real money moves" wherever it is shown.
 * Figures follow the backend's documented settlement model (W = V - D, P = D - F, sum net = W + F + R) so the
 * breakdown reads consistently, but they are fixtures, not calculations performed by the frontend.
 */
import { ApiError } from './errors';
import type { RequestOptions } from './client';
import type {
  BidView, CircleView, CycleView, LedgerEventView, MemberView, ObligationView, ReconciliationView,
  SettlementView,
} from '../types';

export const DEMO_ACTOR = { id: 'demo-alex', role: 'member', displayName: 'Alex' } as const;
export const DEMO_CIRCLE_IDS = { weekend: 'demo-circle-weekend', tech: 'demo-circle-tech' } as const;
export const DEMO_CYCLE_IDS = { weekend: 'demo-cycle-weekend-4', tech: 'demo-cycle-tech-8' } as const;
export const DEMO_SETTLEMENT_ID = 'demo-settlement-weekend-4';

let latencyMs = 140;
/** Tests set this to 0. */
export function setDemoLatency(ms: number) { latencyMs = ms; }

const CUR = 'INR';
const fp = (seed: string) => (seed.repeat(64)).slice(0, 64);

function members(prefix: string, names: string[], winners: number[], alexAt: number): MemberView[] {
  return names.map((name, i) => ({
    id: i + 1 === alexAt ? DEMO_ACTOR.id : `${prefix}-m${i + 1}`,
    name,
    position: i + 1,
    has_won: winners.includes(i + 1),
    security_status: i % 4 === 0 ? 'VERIFIED' : i % 4 === 1 ? 'PENDING' : 'NONE',
  }));
}

const weekendMembers = members('demo-w',
  ['Alex Morgan', 'Priya Nair', 'Ravi Kumar', 'Meera Iyer', 'Sanjay Rao', 'Lakshmi Devi', 'Arjun Reddy', 'Fatima Khan', 'Kiran Patel', 'Anita Joshi'],
  [3, 4, 5], 1);
const techMembers = members('demo-t',
  ['Neha Gupta', 'Omar Sheikh', 'Divya Menon', 'Rahul Verma', 'Sunita Das', 'Vikram Singh', 'Alex Morgan', 'Pooja Shah', 'Imran Ali', 'Tara Bose', 'Naveen Rao', 'Swati Kulkarni'],
  [1, 2, 3, 4, 5, 6, 8, 9], 7);

const CIRCLES: Record<string, CircleView> = {
  [DEMO_CIRCLE_IDS.weekend]: {
    id: DEMO_CIRCLE_IDS.weekend, name: 'Weekend Family Chit #4', organizer_id: DEMO_ACTOR.id, members: weekendMembers,
    rulesets: [{ version: 1, status: 'ACTIVE', fingerprint: fp('4169e1'), reason: 'initial ruleset' }],
  },
  [DEMO_CIRCLE_IDS.tech]: {
    id: DEMO_CIRCLE_IDS.tech, name: 'Tech Colleagues Circle', organizer_id: 'demo-organizer-priya', members: techMembers,
    rulesets: [
      { version: 1, status: 'SUPERSEDED', fingerprint: fp('2f4fc4'), reason: 'initial ruleset' },
      { version: 2, status: 'ACTIVE', fingerprint: fp('b8c4ff'), reason: 'Grace period agreed at the group meeting' },
    ],
  },
};

function obligations(ms: MemberView[], gross: number, dividend: number, paidCount: number): ObligationView[] {
  return ms.map((m, i) => {
    const net = gross - dividend;
    const paid = i < paidCount ? net : 0;
    return { member_id: m.id, gross_due: gross, dividend_credit: dividend, net_payable: net, confirmed_paid: paid, outstanding: net - paid };
  });
}

function weekendObligations(): ObligationView[] {
  // 8 of 10 members confirmed: members 9 and 10 are outstanding.
  return obligations(weekendMembers, 500_000, 15_000, 8);
}
function techObligations(): ObligationView[] {
  // 9 of 12 confirmed, but Alex (position 7) is NOT among them so the Home "due" card has something real to show.
  return techMembers.map((m, i) => {
    const paid = m.id !== DEMO_ACTOR.id && i < 10 ? 1_000_000 : 0;
    return { member_id: m.id, gross_due: 1_000_000, dividend_credit: 0, net_payable: 1_000_000, confirmed_paid: paid, outstanding: 1_000_000 - paid };
  });
}

const CYCLES: Record<string, CycleView> = {
  [DEMO_CYCLE_IDS.weekend]: {
    id: DEMO_CYCLE_IDS.weekend, circle_id: DEMO_CIRCLE_IDS.weekend, number: 4, ruleset_version: 1,
    state: 'AWAITING_APPROVAL', prior_state: null, due_date: '2026-10-15T00:00:00+00:00',
    payout_method: 'SEALED_BID_AUCTION', winner_member_id: weekendMembers[5].id, discount: 400_000,
    obligations: weekendObligations(),
    transitions: [
      { from: 'DRAFT', to: 'OPEN', actor: DEMO_ACTOR.id, reason: null, at: '2026-10-01T06:00:00+00:00' },
      { from: 'OPEN', to: 'COLLECTIONS_IN_PROGRESS', actor: DEMO_ACTOR.id, reason: null, at: '2026-10-01T06:00:01+00:00' },
      { from: 'COLLECTIONS_IN_PROGRESS', to: 'AUCTION_OPEN', actor: DEMO_ACTOR.id, reason: null, at: '2026-10-12T09:00:00+00:00' },
      { from: 'AUCTION_OPEN', to: 'AUCTION_CLOSED', actor: DEMO_ACTOR.id, reason: 'auction closed; bids revealed', at: '2026-10-15T18:00:00+00:00' },
      { from: 'AUCTION_CLOSED', to: 'SETTLEMENT_CALCULATED', actor: DEMO_ACTOR.id, reason: null, at: '2026-10-16T08:30:00+00:00' },
      { from: 'SETTLEMENT_CALCULATED', to: 'AWAITING_APPROVAL', actor: 'system', reason: null, at: '2026-10-16T08:30:01+00:00' },
    ],
  },
  [DEMO_CYCLE_IDS.tech]: {
    id: DEMO_CYCLE_IDS.tech, circle_id: DEMO_CIRCLE_IDS.tech, number: 8, ruleset_version: 2,
    state: 'COLLECTIONS_IN_PROGRESS', prior_state: null, due_date: '2026-11-01T00:00:00+00:00',
    payout_method: null, winner_member_id: null, discount: null,
    obligations: techObligations(),
    transitions: [
      { from: 'DRAFT', to: 'OPEN', actor: 'demo-organizer-priya', reason: null, at: '2026-10-20T06:00:00+00:00' },
      { from: 'OPEN', to: 'COLLECTIONS_IN_PROGRESS', actor: 'demo-organizer-priya', reason: null, at: '2026-10-20T06:00:01+00:00' },
    ],
  },
};

function ledger(cycleId: string, ms: MemberView[], gross: number, paidMinor: number, paidIds: string[], day0: string,
                withSettlement: boolean): LedgerEventView[] {
  const out: LedgerEventView[] = [];
  const base = Date.parse(day0);
  const iso = (offsetHours: number) => new Date(base + offsetHours * 3_600_000).toISOString();
  const cyc = cycleId.replace('demo-cycle-', '');
  ms.forEach((m) => out.push({
    id: `demo-ev-due-${cyc}-${m.id}`, type: 'CONTRIBUTION_DUE', member_id: m.id, amount: gross, currency: CUR,
    timestamp: iso(0), actor: 'demo-organizer', ruleset_version: 1, settlement_id: null, provider_ref: null,
    reverses: null, reason: null,
    journal: { currency: CUR, postings: [
      { account: `MEMBER_RECEIVABLE:${m.id}`, debit: gross, credit: 0 }, { account: 'CIRCLE_POOL', debit: 0, credit: gross }] },
  }));
  paidIds.forEach((id, i) => out.push({
    id: `demo-ev-pay-${cyc}-${id}`, type: 'PAYMENT_CONFIRMED', member_id: id, amount: paidMinor, currency: CUR,
    timestamp: iso(48 + i * 7), actor: 'provider', ruleset_version: 1, settlement_id: null,
    provider_ref: `DEMO-TXN-${cyc.toUpperCase()}-${String(i + 1).padStart(3, '0')}`, reverses: null, reason: null,
    journal: { currency: CUR, postings: [
      { account: 'CASH_CLEARING', debit: paidMinor, credit: 0 }, { account: `MEMBER_RECEIVABLE:${id}`, debit: 0, credit: paidMinor }] },
  }));
  if (withSettlement) {
    ms.forEach((m) => out.push({
      id: `demo-ev-div-${cyc}-${m.id}`, type: 'DIVIDEND_CREDITED', member_id: m.id, amount: 15_000, currency: CUR,
      timestamp: iso(380), actor: 'system', ruleset_version: 1, settlement_id: DEMO_SETTLEMENT_ID, provider_ref: null,
      reverses: null, reason: 'dividend share', journal: null,
    }));
    out.push({
      id: `demo-ev-com-${cyc}`, type: 'COMMISSION_ALLOCATED', member_id: null, amount: 250_000, currency: CUR,
      timestamp: iso(380), actor: 'system', ruleset_version: 1, settlement_id: DEMO_SETTLEMENT_ID, provider_ref: null,
      reverses: null, reason: 'organizer commission', journal: null,
    });
  }
  return out.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

const LEDGERS: Record<string, () => LedgerEventView[]> = {
  [DEMO_CYCLE_IDS.weekend]: () => ledger(DEMO_CYCLE_IDS.weekend, weekendMembers, 500_000, 485_000,
    weekendMembers.slice(0, 8).map((m) => m.id), '2026-10-01T06:00:00Z', true),
  [DEMO_CYCLE_IDS.tech]: () => ledger(DEMO_CYCLE_IDS.tech, techMembers, 1_000_000, 1_000_000,
    techMembers.filter((m, i) => m.id !== DEMO_ACTOR.id && i < 10).map((m) => m.id), '2026-10-20T06:00:00Z', false),
};

const m = (minor: number) => ({ minor, currency: CUR });
const perMember = (minor: number) => Object.fromEntries(weekendMembers.map((x) => [x.id, m(minor)]));

const SETTLEMENT: SettlementView = {
  id: DEMO_SETTLEMENT_ID, cycle_id: DEMO_CYCLE_IDS.weekend, status: 'CALCULATED', ruleset_version: 1,
  provider_payout_ref: null, payout_reference: `payout:${DEMO_SETTLEMENT_ID}`, payout_requested_at: null, finalized_at: null,
  settlement: {
    circle_id: DEMO_CIRCLE_IDS.weekend, cycle_id: DEMO_CYCLE_IDS.weekend, ruleset_version: 1,
    ruleset_fingerprint: fp('4169e1'), currency: CUR, payout_method: 'SEALED_BID_AUCTION',
    winner_member_id: weekendMembers[5].id, member_order: weekendMembers.map((x) => x.id),
    chit_value: m(5_000_000), discount: m(400_000), winner_payout: m(4_600_000), commission: m(250_000),
    dividend_pool: m(150_000), contributions: perMember(500_000), dividends: perMember(15_000),
    net_contributions: perMember(485_000), rounding_remainder: m(0), remainder_destination: null, adjustments: [],
  },
};

const RECON: ReconciliationView = {
  is_clean: false,
  payments: {
    is_clean: false, unresolved: false,
    discrepancies: weekendMembers.slice(8).map((x) => ({
      code: 'UNDERPAID', detail: 'net due 485000 vs cash 0', member_id: x.id })),
  },
  payout: { is_clean: false, unresolved: true, discrepancies: [] },
  ledger_problems: [],
};

const BIDS: BidView[] = [
  { bid_id: 'demo-bid-1', member_id: weekendMembers[5].id, discount: 400_000, accepted: true, reasons: [] },
  { bid_id: 'demo-bid-2', member_id: weekendMembers[7].id, discount: 350_000, accepted: true, reasons: [] },
  { bid_id: 'demo-bid-3', member_id: weekendMembers[8].id, discount: 300_000, accepted: true, reasons: [] },
];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function demoRequest<T>(path: string, opts: RequestOptions): Promise<T> {
  if (latencyMs) await sleep(latencyMs);
  if (opts.signal?.aborted) throw new ApiError('aborted', 0, 'Request cancelled');
  const method = opts.method ?? 'GET';
  if (method !== 'GET') {
    throw new ApiError('unavailable', 501, 'Changes are not available in demo mode.');
  }
  const seg = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  const notFound = (what: string) => new ApiError('not_found', 404, `${what} not found`, 'NOT_FOUND');
  const clone = <V,>(v: V): V => JSON.parse(JSON.stringify(v)) as V;

  if (seg[0] === 'health') return { status: 'ok (demo data)' } as T;
  if (seg[0] === 'circles' && seg.length === 2) {
    const c = CIRCLES[seg[1]];
    if (!c) throw notFound('circle');
    return clone(c) as T;
  }
  if (seg[0] === 'cycles' && seg.length === 2) {
    const c = CYCLES[seg[1]];
    if (!c) throw notFound('cycle');
    return clone(c) as T;
  }
  if (seg[0] === 'cycles' && seg[2] === 'ledger') {
    const l = LEDGERS[seg[1]];
    if (!l) throw notFound('cycle');
    return l() as T;
  }
  if (seg[0] === 'cycles' && seg[2] === 'auction' && seg[3] === 'bids') {
    if (!CYCLES[seg[1]]) throw notFound('cycle');
    return clone(seg[1] === DEMO_CYCLE_IDS.weekend ? BIDS : []) as T;
  }
  if (seg[0] === 'settlements' && seg.length === 2) {
    if (seg[1] !== DEMO_SETTLEMENT_ID) throw notFound('settlement');
    return clone(SETTLEMENT) as T;
  }
  if (seg[0] === 'settlements' && seg[2] === 'reconciliation') {
    if (seg[1] !== DEMO_SETTLEMENT_ID) throw notFound('settlement');
    return clone(RECON) as T;
  }
  throw new ApiError('unavailable', 501, 'This endpoint is not available in demo mode.');
}
