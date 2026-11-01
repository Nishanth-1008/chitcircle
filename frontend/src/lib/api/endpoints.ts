/**
 * Read endpoints used in Phases 1-2. Every function maps 1:1 to an existing FastAPI route.
 *
 * Phase 3 (write paths) will add: POST /circles, POST /circles/{id}/cycles, POST /cycles/{id}/open,
 * POST /cycles/{id}/auction/open|bids|close, POST /cycles/{id}/settlement, POST /settlements/{id}/approvals ...
 * Intentionally NOT present yet. `/webhooks/provider` is server-to-server and must never be called from here.
 */
import { request, type ApiContext } from './client';
import type {
  BidView, CircleView, CycleView, HealthView, LedgerEventView, ReconciliationView, SettlementView,
} from '../types';

const id = encodeURIComponent;

export const api = {
  health: (ctx: ApiContext, signal?: AbortSignal) => request<HealthView>(ctx, '/health', { signal }),
  getCircle: (ctx: ApiContext, circleId: string, signal?: AbortSignal) =>
    request<CircleView>(ctx, `/circles/${id(circleId)}`, { signal }),
  createCircle: (ctx: ApiContext, data: { name: string; ruleset: Record<string, unknown>; members: string[] }, signal?: AbortSignal) =>
    request<{ id: string; name: string; organizer_id: string; ruleset_version: number; members: { id: string; name: string; position: number }[] }>(
      ctx, '/circles', { method: 'POST', body: data, signal }
    ),
  createCycle: (ctx: ApiContext, circleId: string, data: { due_date: string; ruleset_version?: number }, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/circles/${id(circleId)}/cycles`, { method: 'POST', body: data, signal }),
  getCycle: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}`, { signal }),
  openCycle: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/open`, { method: 'POST', signal }),
  openAuction: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/auction/open`, { method: 'POST', signal }),
  submitBid: (ctx: ApiContext, cycleId: string, data: { member_id: string; discount: number }, signal?: AbortSignal) =>
    request<BidView>(ctx, `/cycles/${id(cycleId)}/auction/bids`, { method: 'POST', body: data, signal }),
  closeAuction: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/auction/close`, { method: 'POST', signal }),
  selectRecipient: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}/recipient`, { method: 'POST', signal }),
  calculateSettlement: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<SettlementView>(ctx, `/cycles/${id(cycleId)}/settlement`, { method: 'POST', signal }),
  getLedger: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<LedgerEventView[]>(ctx, `/cycles/${id(cycleId)}/ledger`, { signal }),
  listBids: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<BidView[]>(ctx, `/cycles/${id(cycleId)}/auction/bids`, { signal }),
  getSettlement: (ctx: ApiContext, settlementId: string, signal?: AbortSignal) =>
    request<SettlementView>(ctx, `/settlements/${id(settlementId)}`, { signal }),
  approveSettlement: (ctx: ApiContext, settlementId: string, data: { decision: string; reason?: string }, signal?: AbortSignal) =>
    request<{ status: string }>(ctx, `/settlements/${id(settlementId)}/approvals`, { method: 'POST', body: data, signal }),
  executePayout: (ctx: ApiContext, settlementId: string, signal?: AbortSignal) =>
    request<{ status: string; payout_reference: string }>(ctx, `/settlements/${id(settlementId)}/payout`, { method: 'POST', signal }),
  getReconciliation: (ctx: ApiContext, settlementId: string, signal?: AbortSignal) =>
    request<ReconciliationView>(ctx, `/settlements/${id(settlementId)}/reconciliation`, { signal }),
};
