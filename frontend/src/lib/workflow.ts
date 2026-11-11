/** Role-aware "what happens next" derived from server state. Decides what to SHOW; the server decides what is allowed. */
import type { IconName } from '@/components/Icon';
import { agentsHref, circleCycleHref, circleHref, settlementHref } from './routes';
import { isAuction } from './ruleset';
import type { CycleState, CycleSummary, MyCircle } from './types';

export const ACTIVE_POLL_STATES: CycleState[] = ['AUCTION_OPEN', 'PAYOUT_PENDING', 'PAYOUT_SUBMITTED', 'AWAITING_APPROVAL'];

export const PRE_PAYMENT_STATES: CycleState[] = ['DRAFT', 'OPEN'];

/**
 * In auction circles the installment is final only after settlement (the dividend credit lowers it), so
 * paying earlier would overpay. Rotation and lottery installments are final once collections open.
 */
export function paymentOpen(payoutMode: string, cycle: Pick<CycleSummary, 'state' | 'settlement_id'>): boolean {
  if (PRE_PAYMENT_STATES.includes(cycle.state) || cycle.state === 'FINALIZED') return false;
  return isAuction(payoutMode) ? !!cycle.settlement_id : true;
}

export interface Attention {
  id: string;
  icon: IconName;
  tone: 'brand' | 'warning' | 'danger' | 'info';
  title: string;
  body: string;
  href: string;
}

export function circleAttention(c: MyCircle): Attention[] {
  const out: Attention[] = [];
  const base = circleHref(c.id);
  const org = c.my_role === 'organizer';
  if (org && c.pending_actions > 0) {
    out.push({ id: `${c.id}:agents`, icon: 'bot', tone: 'brand', title: `${c.pending_actions} proposed action${c.pending_actions === 1 ? '' : 's'} to review`,
      body: `${c.name} · collections agent`, href: agentsHref(c.id) });
  }
  const cy = c.current_cycle;
  if (!cy) {
    if (org) out.push({ id: `${c.id}:start`, icon: 'play', tone: 'brand', title: 'Start the first round', body: c.name, href: base });
    return out;
  }
  const round = circleCycleHref(c.id, cy.id);
  const label = `${c.name} · Round ${cy.number}`;
  const settlement = cy.settlement_id ? settlementHref(cy.settlement_id) : round;
  if (c.my_member_id && cy.my_outstanding && cy.my_outstanding > 0 && paymentOpen(c.payout_mode, cy)) {
    out.push({ id: `${cy.id}:pay`, icon: 'wallet', tone: 'warning', title: 'Your contribution is due', body: label, href: round });
  }
  switch (cy.state) {
    case 'DRAFT':
      if (org) out.push({ id: `${cy.id}:open`, icon: 'play', tone: 'brand', title: 'Open collections', body: label, href: round });
      break;
    case 'COLLECTIONS_IN_PROGRESS':
      if (org && !cy.winner_member_id) {
        out.push({ id: `${cy.id}:next`, icon: isAuction(c.payout_mode) ? 'gavel' : 'trophy', tone: 'brand',
          title: isAuction(c.payout_mode) ? 'Open the auction' : 'Select this round’s recipient', body: label, href: round });
      } else if (org) {
        out.push({ id: `${cy.id}:settle`, icon: 'scale', tone: 'brand', title: 'Calculate the settlement', body: label, href: round });
      }
      break;
    case 'AUCTION_OPEN':
      out.push({ id: `${cy.id}:auction`, icon: 'gavel', tone: 'brand',
        title: org ? 'Auction is open — close it when bidding ends' : 'Auction is open — place your bid', body: label, href: round });
      break;
    case 'AUCTION_CLOSED':
      if (org) out.push({ id: `${cy.id}:settle`, icon: 'scale', tone: 'brand', title: 'Calculate the settlement', body: label, href: round });
      break;
    case 'AWAITING_APPROVAL':
      if (org) out.push({ id: `${cy.id}:approve`, icon: 'checkCircle', tone: 'warning', title: 'Settlement awaiting approval', body: label, href: settlement });
      break;
    case 'APPROVED':
      if (org) out.push({ id: `${cy.id}:payout`, icon: 'arrowUp', tone: 'brand', title: 'Release the payout', body: label, href: settlement });
      break;
    case 'PAYOUT_PENDING':
    case 'PAYOUT_SUBMITTED':
      if (org) out.push({ id: `${cy.id}:confirm`, icon: 'clock', tone: 'info', title: 'Payout waiting for provider confirmation', body: label, href: settlement });
      break;
    case 'PAYOUT_CONFIRMED':
    case 'RECONCILIATION_PENDING':
      if (org) out.push({ id: `${cy.id}:finalize`, icon: 'scale', tone: 'brand', title: 'Reconcile and finalize the round', body: label, href: settlement });
      break;
    case 'FINALIZED':
      if (org && c.won_count < c.member_count) {
        out.push({ id: `${cy.id}:nextround`, icon: 'play', tone: 'brand', title: `Start round ${cy.number + 1}`, body: c.name, href: base });
      }
      break;
    case 'ON_HOLD':
    case 'FAILED':
    case 'DISPUTED':
      out.push({ id: `${cy.id}:exception`, icon: 'alert', tone: 'danger',
        title: cy.state === 'DISPUTED' ? 'A dispute is open' : cy.state === 'FAILED' ? 'Something failed' : 'Round is on hold',
        body: label, href: round });
      break;
    default:
      break;
  }
  return out;
}
