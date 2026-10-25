/** Response shapes of the FastAPI financial engine (backend/app/services/financial_service.py). */

export type SecurityStatus = 'NONE' | 'PENDING' | 'VERIFIED' | 'INVALID';

export interface MemberView {
  id: string;
  name: string;
  position: number;
  has_won: boolean;
  security_status: SecurityStatus | string;
}

export interface RulesetVersionView {
  version: number;
  status: 'DRAFT' | 'ACTIVE' | 'SUPERSEDED' | string;
  fingerprint: string;
  reason: string | null;
}

export interface CircleView {
  id: string;
  name: string;
  organizer_id: string;
  members: MemberView[];
  rulesets: RulesetVersionView[];
}

export type CycleState =
  | 'DRAFT' | 'OPEN' | 'COLLECTIONS_IN_PROGRESS' | 'AUCTION_OPEN' | 'AUCTION_CLOSED'
  | 'SETTLEMENT_CALCULATED' | 'AWAITING_APPROVAL' | 'APPROVED' | 'PAYOUT_PENDING' | 'PAYOUT_SUBMITTED'
  | 'PAYOUT_CONFIRMED' | 'RECONCILIATION_PENDING' | 'FINALIZED' | 'ON_HOLD' | 'FAILED' | 'DISPUTED';

export interface ObligationView {
  member_id: string;
  gross_due: number;
  dividend_credit: number;
  net_payable: number;
  confirmed_paid: number;
  outstanding: number;
}

export interface TransitionView {
  from: string;
  to: string;
  actor: string;
  reason: string | null;
  at: string;
}

export interface CycleView {
  id: string;
  circle_id: string;
  number: number;
  ruleset_version: number;
  state: CycleState;
  prior_state: CycleState | null;
  due_date: string;
  payout_method: string | null;
  winner_member_id: string | null;
  /** minor units */
  discount: number | null;
  /** Present on GET /cycles/{id}; the API returns no currency here (see lib/api/currency.ts). */
  obligations?: ObligationView[];
  transitions?: TransitionView[];
}

export interface PostingView { account: string; debit: number; credit: number }
export interface JournalView { currency: string; postings: PostingView[] }

export type LedgerEventType =
  | 'CONTRIBUTION_DUE' | 'PAYMENT_CONFIRMED' | 'PAYMENT_FAILED' | 'DIVIDEND_CREDITED' | 'COMMISSION_ALLOCATED'
  | 'PAYOUT_REQUESTED' | 'PAYOUT_CONFIRMED' | 'REFUND_CONFIRMED' | 'ADJUSTMENT_RECORDED'
  | 'SETTLEMENT_FINALIZED' | 'DISPUTE_OPENED' | 'DISPUTE_RESOLVED';

export interface LedgerEventView {
  id: string;
  type: LedgerEventType | string;
  member_id: string | null;
  amount: number;
  currency: string;
  timestamp: string;
  actor: string;
  ruleset_version: number;
  settlement_id: string | null;
  provider_ref: string | null;
  reverses: string | null;
  reason: string | null;
  journal: JournalView | null;
}

export interface MoneyView { minor: number; currency: string }

export interface AdjustmentView {
  cycle_id: string;
  currency: string;
  calculation: string;
  reason: string;
  rule_version: number;
  amount: MoneyView;
  destination: string | null;
}

export interface SettlementData {
  circle_id: string;
  cycle_id: string;
  ruleset_version: number;
  ruleset_fingerprint: string;
  currency: string;
  payout_method: string;
  winner_member_id: string;
  member_order: string[];
  chit_value: MoneyView;
  discount: MoneyView;
  winner_payout: MoneyView;
  commission: MoneyView;
  dividend_pool: MoneyView;
  contributions: Record<string, MoneyView>;
  dividends: Record<string, MoneyView>;
  net_contributions: Record<string, MoneyView>;
  rounding_remainder: MoneyView;
  remainder_destination: string | null;
  adjustments: AdjustmentView[];
}

export interface SettlementView {
  id: string;
  cycle_id: string;
  status: string;
  ruleset_version: number;
  settlement: SettlementData;
  provider_payout_ref: string | null;
  payout_reference: string;
  payout_requested_at: string | null;
  finalized_at: string | null;
}

export interface BidView {
  bid_id: string;
  member_id: string;
  accepted: boolean;
  /** null when sealed */
  discount: number | null;
  reasons?: string[];
  sealed?: boolean;
}

export interface DiscrepancyView { code: string; detail: string; member_id: string | null }
export interface PartReport { is_clean: boolean; unresolved: boolean; discrepancies: DiscrepancyView[] }
export interface LedgerProblem { code: string; member_id?: string; event_id?: string; detail?: string }

export interface ReconciliationView {
  is_clean: boolean;
  payments: PartReport;
  payout: PartReport;
  ledger_problems: LedgerProblem[];
}

export interface HealthView { status: string }
