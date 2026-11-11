/** Response shapes of the FastAPI backend (backend/app/services/*). Money is always integer minor units. */

export type SecurityStatus = 'NONE' | 'PENDING' | 'VERIFIED' | 'INVALID';
export type CircleRole = 'organizer' | 'member' | 'none';
export type PayoutMode = 'SEALED_BID_AUCTION' | 'OPEN_BID_AUCTION' | 'FIXED_ROTATION' | 'LOTTERY';

export interface UserView {
  id: string;
  email: string | null;
  name: string;
  role: string;
  payout_email: string | null;
  payout_email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  role: string;
  expires_in: number;
  user: UserView;
}

export interface AppConfigView {
  environment: string;
  sandbox_tools: boolean;
  payment_gateway: 'paypal' | 'mock';
}

export interface MemberView {
  id: string;
  name: string;
  position: number;
  has_won: boolean;
  security_status: SecurityStatus | string;
  user_id: string | null;
  linked: boolean;
  invite_email?: string | null;
}

export interface RulesetData {
  currency: string;
  total_chit_value: number;
  member_count: number;
  payout_mode: PayoutMode | string;
  commission: { base: string; rate: string | null; fixed_amount: number | null; rounding: string };
  dividend: { allocation: string };
  auction: { max_discount_rate: string; tie_break: string; no_bid_fallback: string; min_discount: number; increment: number } | null;
  grace_period_days: number;
  rounding: { contribution_remainder: string; remainder_destination: string | null };
  required_approvals: number;
  require_security: boolean;
  require_full_collection_before_payout: boolean;
  one_win_per_member: boolean;
  jurisdiction_profile: string;
  effective_date: string;
  allow_agreed_discount: boolean;
}

export interface RulesetVersionView {
  version: number;
  status: 'DRAFT' | 'ACTIVE' | 'SUPERSEDED' | string;
  fingerprint: string;
  reason: string | null;
  created_at: string | null;
}

export interface CircleView {
  id: string;
  name: string;
  organizer_id: string;
  created_at: string | null;
  my_role: CircleRole;
  my_member_id: string | null;
  currency: string;
  ruleset_version: number;
  ruleset: RulesetData;
  members: MemberView[];
  rulesets: RulesetVersionView[];
}

export type CycleState =
  | 'DRAFT' | 'OPEN' | 'COLLECTIONS_IN_PROGRESS' | 'AUCTION_OPEN' | 'AUCTION_CLOSED'
  | 'SETTLEMENT_CALCULATED' | 'AWAITING_APPROVAL' | 'APPROVED' | 'PAYOUT_PENDING' | 'PAYOUT_SUBMITTED'
  | 'PAYOUT_CONFIRMED' | 'RECONCILIATION_PENDING' | 'FINALIZED' | 'ON_HOLD' | 'FAILED' | 'DISPUTED';

export interface CycleSummary {
  id: string;
  number: number;
  state: CycleState;
  prior_state: CycleState | null;
  due_date: string;
  ruleset_version: number;
  payout_method: string | null;
  winner_member_id: string | null;
  discount: number | null;
  settlement_id: string | null;
  settlement_status: string | null;
  obligations_total: number;
  obligations_settled: number;
  outstanding_total: number;
  my_outstanding: number | null;
  my_net_payable: number | null;
}

export interface MyCircle {
  id: string;
  name: string;
  organizer_id: string;
  my_role: CircleRole;
  my_member_id: string | null;
  currency: string;
  total_chit_value: number;
  member_count: number;
  won_count: number;
  payout_mode: string;
  pending_actions: number;
  current_cycle: CycleSummary | null;
}

export interface ObligationView {
  member_id: string;
  gross_due: number;
  dividend_credit: number;
  adjustments: number;
  net_payable: number;
  confirmed_paid: number;
  outstanding: number;
}

export interface TransitionView { from: string; to: string; actor: string; reason: string | null; at: string }

export interface CycleView {
  id: string;
  circle_id: string;
  number: number;
  ruleset_version: number;
  state: CycleState;
  prior_state: CycleState | null;
  due_date: string;
  payout_method: string | null;
  payout_mode: string;
  winner_member_id: string | null;
  discount: number | null;
  currency: string;
  settlement_id: string | null;
  settlement_status: string | null;
  obligations: ObligationView[];
  transitions: TransitionView[];
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
  cycle_id?: string | null;
  cycle_number?: number | null;
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

export interface LedgerPage { items: LedgerEventView[]; next_cursor: string | null; has_more: boolean }

export interface MoneyView { minor: number; currency: string }

export interface AdjustmentView {
  cycle_id: string; currency: string; calculation: string; reason: string; rule_version: number;
  amount: MoneyView; destination: string | null;
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

export interface ApprovalView { approver_id: string; decision: string; reason: string | null; created_at: string | null }

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
  circle_id: string;
  circle_name: string;
  organizer_id: string;
  cycle_number: number;
  cycle_state: CycleState;
  prior_state: CycleState | null;
  /** reason recorded with the latest state change (e.g. why a payout failed) */
  state_reason: string | null;
  required_approvals: number;
  require_security: boolean;
  require_full_collection_before_payout: boolean;
  winner_security_status: string | null;
  approvals: ApprovalView[];
}

export interface BidView {
  bid_id: string;
  member_id: string;
  accepted: boolean;
  /** null while sealed */
  discount: number | null;
  reasons?: string[];
  sealed?: boolean;
  submitted_at: string;
}

export interface BidPreview {
  member_id: string;
  currency: string;
  discount_minor: number;
  reasons: string[];
  valid: boolean;
  chit_value_minor: number;
  cap_minor: number;
  min_discount_minor: number;
  increment_minor: number;
  discount_rate: string;
  preview: null | {
    you_receive_minor: number;
    commission_minor: number;
    dividend_pool_minor: number;
    your_dividend_minor: number;
    your_net_contribution_minor: number;
  };
  history: { cycle_number: number; discount_minor: number; discount_rate: string }[];
  note: string;
}

export interface ExplanationView {
  member_id: string;
  cycle_id: string;
  currency: string;
  is_winner: boolean;
  lines: { label: string; amount_minor: number; note: string }[];
  summary: string;
  source_event_ids: string[];
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

export interface DashboardView {
  circle_id: string;
  circle_name: string;
  summary: {
    total_members: number; won_members: number; remaining_members: number; total_cycles: number;
    completed_cycles: number; current_cycle_id: string | null; current_cycle_number: number;
    current_cycle_state: CycleState | null; current_cycle_due_date: string | null;
  };
  collections: { collected: number; outstanding: number; late: number; total_members: number;
    amount_collected: number; amount_outstanding: number };
  auctions: { completed: number; pending: number; current_state: string | null };
  payouts: { completed: number; pending: number; failed: number };
  risk: { late_members_count: number; late_members: { member_id: string; member_name: string | null;
    outstanding: number; due_date: string | null; is_late: boolean }[] };
  security: { pending: number; verified: number };
  recent_activity: { event_id: string; event_type: string; amount: number; currency: string; timestamp: string;
    member_id: string | null; member_name: string | null; cycle_id: string | null }[];
}

export type TimelineCellState = 'PAID' | 'LATE' | 'PENDING' | 'WINNER' | 'AUCTION' | 'NOT_OPEN';

export interface TimelineView {
  circle_id: string;
  circle_name: string;
  members: {
    member_id: string; member_name: string; position: number; has_won: boolean; security_status: string;
    user_id: string | null;
    cycles: { cycle_id: string; cycle_number: number; due_date: string | null; state: TimelineCellState;
      amount_due: number; amount_paid: number; dividend: number; is_winner: boolean; discount: number | null;
      paid_state?: TimelineCellState }[];
  }[];
  cycles: { cycle_id: string; cycle_number: number; state: CycleState; due_date: string | null;
    winner_member_id: string | null; discount: number | null; settlement_status: string | null }[];
}

export interface RiskView {
  member_id: string; indicator: string; points: number; factors: string[]; required_security_level: string;
  organizer_alert: boolean; review_recommendation: string; disclaimer: string;
}

export interface MandateSummary {
  id: string; state: string; cap_minor: number; expires_at: string; outcome: Record<string, unknown> | null;
}

export interface ProposedActionView {
  id: string;
  kind: 'invoice' | 'reminder' | 'payout' | string;
  params: {
    member_id: string; member_name?: string; amount_minor: number; currency: string; cycle_id: string;
    cycle_number?: number; due_date?: string; days_overdue?: number; stage?: string; message?: string;
    settlement_id?: string;
  };
  rationale: string | null;
  state: 'PROPOSED' | 'APPROVED' | 'REJECTED' | string;
  proposed_by: string;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  mandate: MandateSummary | null;
}

export interface CollectionResult {
  status: string; provider_ref: string | null; approval_url: string | null; detail: string;
  amount: number; currency: string;
}

export interface PayoutResult {
  outcome: 'SUBMITTED' | 'HELD' | 'FAILED' | 'UNRESOLVED' | 'ALREADY_REQUESTED' | string;
  provider_ref?: string; reasons?: string[]; detail?: string; cycle_state?: string; note?: string;
}

export interface ProviderApplyResult {
  duplicate: boolean; applied?: string; cycle_state?: string; sandbox?: boolean; confirmed_paid?: number;
}
