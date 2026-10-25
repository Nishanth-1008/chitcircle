'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { DataBoundary, FinancialBreakdown } from '@/components/domain';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Banner, Skeleton, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { PAYOUT_GATEWAY } from '@/lib/config';
import { memberName } from '@/lib/derive';
import { formatDateTime } from '@/lib/format';
import { useApi } from '@/lib/hooks';
import { sessionKey, useSession } from '@/lib/session';
import { stateInfo } from '@/lib/status';

export default function SettlementPage() {
  const { settlementId } = useParams<{ settlementId: string }>();
  const ctx = useSession();
  const k = sessionKey(ctx);
  const settlement = useApi(`settlement:${k}:${settlementId}`, (s) => api.getSettlement(ctx, settlementId, s));
  const cycleId = settlement.data?.cycle_id ?? null;
  const cycle = useApi(cycleId ? `cycle:${k}:${cycleId}` : null, (s) => api.getCycle(ctx, cycleId!, s));
  const circleId = settlement.data?.settlement.circle_id ?? null;
  const circle = useApi(circleId ? `circle:${k}:${circleId}` : null, (s) => api.getCircle(ctx, circleId!, s));
  const recon = useApi(`recon:${k}:${settlementId}`, (s) => api.getReconciliation(ctx, settlementId, s));

  const back = circleId && cycleId ? `/app/circles/${encodeURIComponent(circleId)}/cycles/${encodeURIComponent(cycleId)}` : '/app/circles';
  const info = cycle.data ? stateInfo(cycle.data.state) : undefined;

  return (
    <Screen title="Settlement" back={back}>
      <DataBoundary state={settlement} skeleton={<Skeleton count={3} />}>
        {(st) => (
          <>
            <section className="card stack" aria-label="Settlement status">
              <div className="row row--between">
                <div>
                  <p className="circle-card__name">{circle.data?.name ?? 'Settlement'}</p>
                  <p className="muted">{cycle.data ? `Round ${cycle.data.number}` : ' '}</p>
                </div>
                {info ? <StatusPill tone={info.tone}>{info.settlementLabel}</StatusPill> : <StatusPill>Loading…</StatusPill>}
              </div>
              {info && <p className="muted">{info.hint}</p>}
            </section>

            {PAYOUT_GATEWAY === 'stub' && ctx.mode === 'live' && (
              <Banner tone="warning" icon="alert">The payout gateway is a stub in this backend build. A payout status here does not mean real funds moved.</Banner>
            )}
            {ctx.mode === 'demo' && <Banner tone="info" icon="info">These figures are fictional fixtures that follow the backend’s settlement model.</Banner>}

            <FinancialBreakdown data={st.settlement} actorId={ctx.actor?.id} nameOf={(id) => memberName(circle.data, id)} />

            <section className="card stack" aria-label="Payout details">
              <h3>Payout</h3>
              <div className="detail" style={{ padding: 0 }}>
                <dl>
                  <dt>Requested</dt><dd>{st.payout_requested_at ? formatDateTime(st.payout_requested_at) : 'Not requested yet'}</dd>
                  <dt>Provider reference</dt><dd className="num">{st.provider_payout_ref ?? 'None yet'}</dd>
                  <dt>Finalized</dt><dd>{st.finalized_at ? formatDateTime(st.finalized_at) : 'Not finalized'}</dd>
                  <dt>Payout key</dt><dd className="num">{st.payout_reference}</dd>
                </dl>
              </div>
            </section>

            <Link href={`/app/settlements/${encodeURIComponent(settlementId)}/reconciliation`} className="card row" aria-label="Reconciliation">
              <span className={`glyph ${recon.data ? (recon.data.is_clean ? 'glyph--income' : 'glyph--warning') : ''}`}><Icon name={recon.data?.is_clean ? 'checkCircle' : 'scale'} /></span>
              <div className="grow">
                <strong>Reconciliation</strong>
                <p className="muted">{recon.data ? (recon.data.is_clean ? 'No discrepancies found' : 'Not yet reconciled — see what’s open') : recon.error ? 'Couldn’t check right now' : 'Checking…'}</p>
              </div>
              <Icon name="chevronRight" width={18} height={18} />
            </Link>

            <Banner tone="neutral" icon="lock">This screen is read-only. Approval, payout and finalization are separate server actions and aren’t available here yet.</Banner>
          </>
        )}
      </DataBoundary>
    </Screen>
  );
}
