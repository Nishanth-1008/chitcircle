import type { CycleState } from './types';

export type Tone = 'neutral' | 'brand' | 'info' | 'success' | 'warning' | 'danger';

export interface StateInfo {
  label: string;
  tone: Tone;
  /** Plain-language explanation. Never implies funds moved before the provider has confirmed it. */
  hint: string;
  /** Label used on settlement screens (Preview / Awaiting approval / Approved / ...). */
  settlementLabel: string;
  /** Position in the round stepper, or -1 for exception states (use prior_state). */
  phase: number;
}

export const ROUND_STEPS = ['Collect', 'Recipient', 'Settlement', 'Approval', 'Payout', 'Reconcile', 'Finalized'] as const;

export const CYCLE_STATE_INFO: Record<CycleState, StateInfo> = {
  DRAFT: { label: 'Not opened', tone: 'neutral', phase: 0, settlementLabel: 'Not started',
    hint: 'This round exists but contributions have not been opened yet.' },
  OPEN: { label: 'Opening', tone: 'info', phase: 0, settlementLabel: 'Not started',
    hint: 'Contribution obligations are being created for this round.' },
  COLLECTIONS_IN_PROGRESS: { label: 'Collecting', tone: 'info', phase: 0, settlementLabel: 'Not started',
    hint: 'Members are contributing. A contribution counts only once the provider confirms it.' },
  AUCTION_OPEN: { label: 'Auction open', tone: 'brand', phase: 1, settlementLabel: 'Not started',
    hint: 'Bidding is open. The server decides eligibility and the winner.' },
  AUCTION_CLOSED: { label: 'Auction closed', tone: 'brand', phase: 1, settlementLabel: 'Not started',
    hint: 'Bidding has closed and the server has recorded the outcome.' },
  SETTLEMENT_CALCULATED: { label: 'Settlement preview', tone: 'info', phase: 2, settlementLabel: 'Preview',
    hint: 'The server has calculated a settlement. It still needs approval.' },
  AWAITING_APPROVAL: { label: 'Awaiting approval', tone: 'warning', phase: 3, settlementLabel: 'Awaiting approval',
    hint: 'Waiting for the required approvals. Nothing has been paid out.' },
  APPROVED: { label: 'Approved', tone: 'brand', phase: 3, settlementLabel: 'Approved',
    hint: 'Approved. A payout has not been requested or confirmed yet.' },
  PAYOUT_PENDING: { label: 'Payout requested', tone: 'warning', phase: 4, settlementLabel: 'Payout submitted',
    hint: 'A payout was requested. It is not confirmed until the provider says so.' },
  PAYOUT_SUBMITTED: { label: 'Payout submitted', tone: 'warning', phase: 4, settlementLabel: 'Payout submitted',
    hint: 'Sent to the payout provider. Waiting for provider confirmation.' },
  PAYOUT_CONFIRMED: { label: 'Provider confirmed', tone: 'info', phase: 4, settlementLabel: 'Provider confirmed',
    hint: 'The provider confirmed the payout. Reconciliation is still required.' },
  RECONCILIATION_PENDING: { label: 'Reconciling', tone: 'warning', phase: 5, settlementLabel: 'Reconciliation required',
    hint: 'Checking payments, payout and ledger against each other.' },
  FINALIZED: { label: 'Finalized', tone: 'success', phase: 6, settlementLabel: 'Finalized',
    hint: 'All checks passed and this round is closed.' },
  ON_HOLD: { label: 'On hold', tone: 'danger', phase: -1, settlementLabel: 'Failed or on hold',
    hint: 'This round is paused. The organizer must resolve it before it can continue.' },
  FAILED: { label: 'Failed', tone: 'danger', phase: -1, settlementLabel: 'Failed or on hold',
    hint: 'Something failed, for example a payout. Funds should not be assumed to have moved.' },
  DISPUTED: { label: 'Disputed', tone: 'danger', phase: -1, settlementLabel: 'Failed or on hold',
    hint: 'A dispute is open on this round.' },
};

export function stateInfo(state: string): StateInfo {
  return (CYCLE_STATE_INFO as Record<string, StateInfo>)[state] ?? {
    label: humanize(state), tone: 'neutral', phase: -1, settlementLabel: humanize(state),
    hint: 'Status reported by the server.',
  };
}

/** Phase index for the stepper; exception states use the state the round was in before. */
export function phaseOf(state: string, priorState: string | null): number {
  const info = stateInfo(state);
  if (info.phase >= 0) return info.phase;
  return priorState ? Math.max(stateInfo(priorState).phase, 0) : 0;
}

export const isExceptionState = (s: string) => s === 'ON_HOLD' || s === 'FAILED' || s === 'DISPUTED';
export const isFinalized = (s: string) => s === 'FINALIZED';

export function humanize(code: string): string {
  const t = code.toLowerCase().replace(/_/g, ' ');
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export const SECURITY_INFO: Record<string, { label: string; tone: Tone }> = {
  NONE: { label: 'No security on file', tone: 'neutral' },
  PENDING: { label: 'Security pending', tone: 'warning' },
  VERIFIED: { label: 'Security verified', tone: 'success' },
  INVALID: { label: 'Security invalid', tone: 'danger' },
};

export const AUCTION_REJECT_REASONS: Record<string, string> = {
  AUCTION_CLOSED: 'The auction is not open.',
  MEMBER_ALREADY_WON: 'This member has already received a payout.',
  IN_ARREARS: 'Overdue contributions past the grace period.',
};
