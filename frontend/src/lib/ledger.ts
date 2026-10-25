import type { IconName } from '@/components/Icon';
import type { Tone } from './status';
import { humanize } from './status';
import type { LedgerEventView } from './types';

export type FilterId = 'all' | 'incoming' | 'outgoing' | 'pending';
export type Direction = 'in' | 'out' | 'none';

export interface LedgerDescription {
  title: string;
  direction: Direction;
  icon: IconName;
  glyph: 'income' | 'expense' | 'warning' | 'neutral';
  status: string;
  statusTone: Tone;
  /** Scheduled/requested items are NOT completed payments. */
  pending: boolean;
}

/**
 * Presentation-only mapping of the backend's ledger event types.
 * A CONTRIBUTION_DUE row is an obligation, not a payment; PAYOUT_REQUESTED is not a payout until the provider
 * confirms it (PAYOUT_CONFIRMED). Direction/colour are display conventions, not accounting logic.
 */
export function describeLedgerEvent(e: Pick<LedgerEventView, 'type' | 'reverses'>): LedgerDescription {
  const base = ((): LedgerDescription => {
    switch (e.type) {
      case 'PAYMENT_CONFIRMED':
        return { title: 'Contribution received', direction: 'in', icon: 'arrowDown', glyph: 'income', status: 'Provider confirmed', statusTone: 'success', pending: false };
      case 'PAYMENT_FAILED':
        return { title: 'Payment failed', direction: 'none', icon: 'alert', glyph: 'expense', status: 'Failed', statusTone: 'danger', pending: false };
      case 'CONTRIBUTION_DUE':
        return { title: 'Contribution due', direction: 'none', icon: 'calendar', glyph: 'warning', status: 'Scheduled · not paid', statusTone: 'warning', pending: true };
      case 'DIVIDEND_CREDITED':
        return { title: 'Dividend credited', direction: 'in', icon: 'wallet', glyph: 'income', status: 'Credited', statusTone: 'success', pending: false };
      case 'COMMISSION_ALLOCATED':
        return { title: 'Organizer commission', direction: 'none', icon: 'receipt', glyph: 'neutral', status: 'Allocated', statusTone: 'neutral', pending: false };
      case 'PAYOUT_REQUESTED':
        return { title: 'Payout requested', direction: 'out', icon: 'arrowUp', glyph: 'warning', status: 'Not confirmed', statusTone: 'warning', pending: true };
      case 'PAYOUT_CONFIRMED':
        return { title: 'Payout confirmed', direction: 'out', icon: 'trophy', glyph: 'expense', status: 'Provider confirmed', statusTone: 'success', pending: false };
      case 'REFUND_CONFIRMED':
        return { title: 'Refund confirmed', direction: 'out', icon: 'arrowUp', glyph: 'expense', status: 'Provider confirmed', statusTone: 'success', pending: false };
      case 'ADJUSTMENT_RECORDED':
        return { title: 'Adjustment recorded', direction: 'none', icon: 'scale', glyph: 'neutral', status: 'Recorded', statusTone: 'neutral', pending: false };
      case 'SETTLEMENT_FINALIZED':
        return { title: 'Settlement finalized', direction: 'none', icon: 'checkCircle', glyph: 'income', status: 'Finalized', statusTone: 'success', pending: false };
      case 'DISPUTE_OPENED':
        return { title: 'Dispute opened', direction: 'none', icon: 'alert', glyph: 'expense', status: 'Open', statusTone: 'danger', pending: true };
      case 'DISPUTE_RESOLVED':
        return { title: 'Dispute resolved', direction: 'none', icon: 'check', glyph: 'neutral', status: 'Resolved', statusTone: 'neutral', pending: false };
      default:
        return { title: humanize(e.type), direction: 'none', icon: 'receipt', glyph: 'neutral', status: 'Recorded', statusTone: 'neutral', pending: false };
    }
  })();
  if (e.reverses) return { ...base, title: `Reversal · ${base.title}`, status: 'Reversal', statusTone: 'neutral' };
  return base;
}

export function matchesFilter(e: LedgerEventView, f: FilterId): boolean {
  if (f === 'all') return true;
  const d = describeLedgerEvent(e);
  if (f === 'incoming') return d.direction === 'in';
  if (f === 'outgoing') return d.direction === 'out' && !d.pending;
  return d.pending;
}

export const FILTERS: { id: FilterId; label: string }[] = [
  { id: 'all', label: 'All' }, { id: 'incoming', label: 'Incoming' },
  { id: 'outgoing', label: 'Outgoing' }, { id: 'pending', label: 'Pending' },
];

/** newest first */
export const sortLedger = (events: LedgerEventView[]) =>
  [...events].sort((a, b) => b.timestamp.localeCompare(a.timestamp) || b.id.localeCompare(a.id));

/** First settlement id referenced by a round's ledger, if a settlement has been calculated. */
export const findSettlementId = (events: LedgerEventView[] | undefined) =>
  events?.find((e) => e.settlement_id)?.settlement_id ?? null;
