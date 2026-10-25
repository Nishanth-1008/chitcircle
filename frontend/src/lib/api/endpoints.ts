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
  getCycle: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<CycleView>(ctx, `/cycles/${id(cycleId)}`, { signal }),
  getLedger: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<LedgerEventView[]>(ctx, `/cycles/${id(cycleId)}/ledger`, { signal }),
  listBids: (ctx: ApiContext, cycleId: string, signal?: AbortSignal) =>
    request<BidView[]>(ctx, `/cycles/${id(cycleId)}/auction/bids`, { signal }),
  getSettlement: (ctx: ApiContext, settlementId: string, signal?: AbortSignal) =>
    request<SettlementView>(ctx, `/settlements/${id(settlementId)}`, { signal }),
  getReconciliation: (ctx: ApiContext, settlementId: string, signal?: AbortSignal) =>
    request<ReconciliationView>(ctx, `/settlements/${id(settlementId)}/reconciliation`, { signal }),
};
