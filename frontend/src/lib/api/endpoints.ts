/**
 * Every function maps 1:1 to a FastAPI route. `/webhooks/provider` is server-to-server and is never called here.
 */
import { request, type ApiContext } from './client';
import type {
  AppConfigView, BidPreview, BidView, CircleView, CollectionResult, CycleSummary, CycleView, DashboardView,
  ExplanationView, LedgerPage, MyCircle, PayoutResult, ProposedActionView, ProviderApplyResult,
  ReconciliationView, RiskView, SettlementView, TimelineView, TokenResponse, UserView,
} from '../types';

const id = encodeURIComponent;
type S = AbortSignal | undefined;

export const api = {
  // ------------------------------------------------------------- system & auth
  health: (ctx: ApiContext, signal?: S) => request<{ status: string }>(ctx, '/health', { signal, anonymous: true }),
  config: (ctx: ApiContext, signal?: S) => request<AppConfigView>(ctx, '/config', { signal, anonymous: true }),
  login: (email: string, password: string) =>
    request<TokenResponse>({ token: null }, '/auth/login', {
      method: 'POST', form: { username: email, password }, anonymous: true,
    }),
  register: (data: { email: string; password: string; name: string; role?: string }) =>
    request<TokenResponse>({ token: null }, '/auth/register', { method: 'POST', body: data, anonymous: true }),
  me: (ctx: ApiContext, signal?: S) => request<UserView>(ctx, '/auth/me', { signal }),
  refresh: (ctx: ApiContext) => request<TokenResponse>(ctx, '/auth/refresh', { method: 'POST' }),
  setPayoutEmail: (ctx: ApiContext, email: string) =>
    request<UserView>(ctx, '/auth/me/payout-email', { method: 'PUT', body: { email } }),

  // ------------------------------------------------------------- circles
  myCircles: (ctx: ApiContext, signal?: S) => request<MyCircle[]>(ctx, '/circles', { signal }),
  getCircle: (ctx: ApiContext, circleId: string, signal?: S) => request<CircleView>(ctx, `/circles/${id(circleId)}`, { signal }),
  createCircle: (ctx: ApiContext, data: { name: string; ruleset: Record<string, unknown>; members: unknown[] }) =>
    request<{ id: string }>(ctx, '/circles', { method: 'POST', body: data }),
  listCycles: (ctx: ApiContext, circleId: string, signal?: S) =>
    request<CycleSummary[]>(ctx, `/circles/${id(circleId)}/cycles`, { signal }),
  createCycle: (ctx: ApiContext, circleId: string, dueDate: string) =>
    request<CycleView>(ctx, `/circles/${id(circleId)}/cycles`, { method: 'POST', body: { due_date: dueDate } }),
  dashboard: (ctx: ApiContext, circleId: string, signal?: S) =>
    request<DashboardView>(ctx, `/circles/${id(circleId)}/dashboard`, { signal }),
  timeline: (ctx: ApiContext, circleId: string, signal?: S) =>
    request<TimelineView>(ctx, `/circles/${id(circleId)}/timeline`, { signal }),
  circleLedger: (ctx: ApiContext, circleId: string, q: { cursor?: string | null; cycle_id?: string; limit?: number }, signal?: S) =>
    request<LedgerPage>(ctx, `/circles/${id(circleId)}/ledger`, { query: q, signal }),
  setSecurity: (ctx: ApiContext, circleId: string, memberId: string, status: string) =>
    request<{ member_id: string; security_status: string }>(
      ctx, `/circles/${id(circleId)}/members/${id(memberId)}/security`, { method: 'PUT', body: { status } }),
  memberRisk: (ctx: ApiContext, circleId: string, memberId: string, signal?: S) =>
    request<RiskView>(ctx, `/circles/${id(circleId)}/members/${id(memberId)}/risk`, { signal }),

  // ------------------------------------------------------------- rounds
  getCycle: (ctx: ApiContext, cycleId: string, signal?: S) => request<CycleView>(ctx, `/cycles/${id(cycleId)}`, { signal }),
  openCycle: (ctx: ApiContext, cycleId: string) => request<CycleView>(ctx, `/cycles/${id(cycleId)}/open`, { method: 'POST' }),
  openAuction: (ctx: ApiContext, cycleId: string) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/auction/open`, { method: 'POST' }),
  listBids: (ctx: ApiContext, cycleId: string, signal?: S) => request<BidView[]>(ctx, `/cycles/${id(cycleId)}/auction/bids`, { signal }),
  bidPreview: (ctx: ApiContext, cycleId: string, memberId: string, discount: number, signal?: S) =>
    request<BidPreview>(ctx, `/cycles/${id(cycleId)}/auction/preview`, { query: { member_id: memberId, discount }, signal }),
  submitBid: (ctx: ApiContext, cycleId: string, memberId: string, discount: number) =>
    request<{ bid_id: string; accepted: boolean; reasons: string[] }>(
      ctx, `/cycles/${id(cycleId)}/auction/bids`, { method: 'POST', body: { member_id: memberId, discount } }),
  closeAuction: (ctx: ApiContext, cycleId: string) =>
    request<{ status: string; winner_member_id?: string; fallback?: string }>(ctx, `/cycles/${id(cycleId)}/auction/close`, { method: 'POST' }),
  selectRecipient: (ctx: ApiContext, cycleId: string) =>
    request<{ winner_member_id?: string; status?: string }>(ctx, `/cycles/${id(cycleId)}/recipient`, { method: 'POST' }),
  calculateSettlement: (ctx: ApiContext, cycleId: string) =>
    request<SettlementView>(ctx, `/cycles/${id(cycleId)}/settlement`, { method: 'POST' }),
  cycleLedger: (ctx: ApiContext, cycleId: string, signal?: S) =>
    request<LedgerPage>(ctx, `/cycles/${id(cycleId)}/ledger`, { query: { limit: 200 }, signal }),
  explain: (ctx: ApiContext, cycleId: string, memberId: string, signal?: S) =>
    request<ExplanationView>(ctx, `/cycles/${id(cycleId)}/members/${id(memberId)}/explanation`, { signal }),
  resume: (ctx: ApiContext, cycleId: string, reason: string) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/resume`, { method: 'POST', body: { reason } }),
  openDispute: (ctx: ApiContext, cycleId: string, reason: string) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/disputes`, { method: 'POST', body: { reason } }),
  resolveDispute: (ctx: ApiContext, cycleId: string, reason: string) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/disputes/resolve`, { method: 'POST', body: { reason } }),

  // ------------------------------------------------------------- payments
  createCollection: (ctx: ApiContext, cycleId: string, memberId: string) =>
    request<CollectionResult>(ctx, '/collections/create', { method: 'POST', query: { cycle_id: cycleId, member_id: memberId } }),
  sandboxPayment: (ctx: ApiContext, cycleId: string, memberId: string) =>
    request<ProviderApplyResult>(ctx, `/sandbox/cycles/${id(cycleId)}/payments`, { method: 'POST', body: { member_id: memberId } }),
  sandboxPayout: (ctx: ApiContext, settlementId: string, status: 'COMPLETED' | 'FAILED' = 'COMPLETED') =>
    request<ProviderApplyResult>(ctx, `/sandbox/settlements/${id(settlementId)}/payout`, { method: 'POST', body: { status } }),

  // ------------------------------------------------------------- settlements
  getSettlement: (ctx: ApiContext, settlementId: string, signal?: S) =>
    request<SettlementView>(ctx, `/settlements/${id(settlementId)}`, { signal }),
  approveSettlement: (ctx: ApiContext, settlementId: string, decision: 'APPROVE' | 'REJECT', reason?: string) =>
    request<{ cycle_state: string }>(ctx, `/settlements/${id(settlementId)}/approvals`, { method: 'POST', body: { decision, reason } }),
  executePayout: (ctx: ApiContext, settlementId: string) =>
    request<PayoutResult>(ctx, `/settlements/${id(settlementId)}/payout`, { method: 'POST' }),
  checkPayout: (ctx: ApiContext, settlementId: string) =>
    request<PayoutResult>(ctx, `/settlements/${id(settlementId)}/payout/check`, { method: 'POST' }),
  reconciliation: (ctx: ApiContext, settlementId: string, signal?: S) =>
    request<ReconciliationView>(ctx, `/settlements/${id(settlementId)}/reconciliation`, { signal }),
  finalize: (ctx: ApiContext, settlementId: string) =>
    request<{ reconciliation: ReconciliationView }>(ctx, `/settlements/${id(settlementId)}/finalize`, { method: 'POST' }),

  // ------------------------------------------------------------- agents & mandates
  runCollectionsAgent: (ctx: ApiContext, circleId: string) =>
    request<{ scanned: number; created: unknown[]; skipped: { reason: string }[] }>(
      ctx, `/circles/${id(circleId)}/agents/collections/run`, { method: 'POST' }),
  listProposals: (ctx: ApiContext, circleId: string, signal?: S) =>
    request<ProposedActionView[]>(ctx, `/circles/${id(circleId)}/proposed-actions`, { signal }),
  approveProposal: (ctx: ApiContext, proposalId: string, stepUp: 'OTP' | 'BIOMETRIC', evidence: Record<string, unknown>) =>
    request<{ mandate_id: string; expires_at: string }>(ctx, `/proposed-actions/${id(proposalId)}/approve`, {
      method: 'POST', body: { step_up_method: stepUp, step_up_evidence: evidence },
    }),
  rejectProposal: (ctx: ApiContext, proposalId: string, reason?: string) =>
    request<{ state: string }>(ctx, `/proposed-actions/${id(proposalId)}/reject`, { method: 'POST', body: { reason } }),
  executeMandate: (ctx: ApiContext, mandateId: string) =>
    request<{ outcome: Record<string, unknown> }>(ctx, `/mandates/${id(mandateId)}/execute`, { method: 'POST' }),
  revokeMandate: (ctx: ApiContext, mandateId: string, reason?: string) =>
    request<{ state: string }>(ctx, `/mandates/${id(mandateId)}/revoke`, { method: 'POST', body: { reason } }),
};
