'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { DataBoundary, FinancialBreakdown } from '@/components/domain';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Banner, Button, SectionHead, Skeleton, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { PAYOUT_GATEWAY } from '@/lib/config';
import { memberName } from '@/lib/derive';
import { formatDateTime } from '@/lib/format';
import { useApi, useSingleFlight } from '@/lib/hooks';
import { roleIn } from '@/lib/permissions';
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
  const role = roleIn(circle.data, ctx.actor);
  const [approveMsg, setApproveMsg] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [executePayoutMsg, setExecutePayoutMsg] = useState('');
  const [checkPayoutMsg, setCheckPayoutMsg] = useState('');
  const [finalizeMsg, setFinalizeMsg] = useState('');

  const approveAction = useSingleFlight(async (decision: 'approve' | 'reject') => {
    setApproveMsg('');
    try {
      await api.approveSettlement(ctx, settlementId, { decision, reason: rejectReason || undefined });
      setApproveMsg(`Settlement ${decision === 'approve' ? 'approved' : 'rejected'}.`);
      setRejectReason('');
    } catch (e) { setApproveMsg(describeError(e).message); }
  });

  const executePayoutAction = useSingleFlight(async () => {
    setExecutePayoutMsg('');
    try {
      await api.executePayout(ctx, settlementId);
      setExecutePayoutMsg('Payout executed.');
    } catch (e) { setExecutePayoutMsg(describeError(e).message); }
  });

  const checkPayoutAction = useSingleFlight(async () => {
    setCheckPayoutMsg('');
    try {
      await api.checkPayout(ctx, settlementId);
      setCheckPayoutMsg('Payout status checked.');
    } catch (e) { setCheckPayoutMsg(describeError(e).message); }
  });

  const finalizeAction = useSingleFlight(async () => {
    setFinalizeMsg('');
    try {
      await api.finalizeSettlement(ctx, settlementId);
      setFinalizeMsg('Round finalized.');
    } catch (e) { setFinalizeMsg(describeError(e).message); }
  });

  const canApprove = role === 'organizer' && cycle.data?.state === 'AWAITING_APPROVAL';
  const canPayout = role === 'organizer' && cycle.data?.state === 'APPROVED';
  const canCheckPayout = role === 'organizer' && cycle.data?.state === 'PAYOUT_SUBMITTED';
  const canFinalize = role === 'organizer' && cycle.data?.state === 'RECONCILIATION_PENDING';

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

            {PAYOUT_GATEWAY === 'stub' && (
              <Banner tone="warning" icon="alert">The payout gateway is a stub in this backend build. A payout status here does not mean real funds moved.</Banner>
            )}

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

            {canApprove && (
              <section className="card stack" aria-label="Approve settlement">
                <SectionHead title="Approve settlement" />
                <p className="muted">Approving commits this settlement. A rejected settlement stays open for revision.</p>
                <form className="stack" onSubmit={(e) => { e.preventDefault(); void approveAction.run('approve'); }} noValidate>
                  <div className="field">
                    <label htmlFor="approve-reason">Reason (optional)</label>
                    <textarea id="approve-reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={2} />
                    <span className="field__help">Why you’re approving or rejecting this settlement.</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Button type="submit" variant="primary" disabled={approveAction.pending}>{approveAction.pending ? 'Approving…' : 'Approve'}</Button>
                    <Button type="submit" variant="secondary" onClick={() => void approveAction.run('reject')} disabled={approveAction.pending}>{approveAction.pending ? 'Rejecting…' : 'Reject'}</Button>
                  </div>
                </form>
                {approveMsg && <Banner tone="info">{approveMsg}</Banner>}
              </section>
            )}

            {canPayout && (
              <section className="card stack" aria-label="Execute payout">
                <SectionHead title="Execute payout" />
                <p className="muted">Request the payout to the winner through the configured provider.</p>
                {PAYOUT_GATEWAY === 'stub' && <Banner tone="warning" icon="alert">Payout gateway is a stub — no real funds move.</Banner>}
                {executePayoutMsg && <Banner tone="info">{executePayoutMsg}</Banner>}
                <Button variant="primary" disabled={executePayoutAction.pending} onClick={() => void executePayoutAction.run()}>
                  {executePayoutAction.pending ? 'Executing…' : 'Execute Payout'}
                </Button>
              </section>
            )}

            {canCheckPayout && (
              <section className="card stack" aria-label="Check payout status">
                <SectionHead title="Check payout status" />
                <p className="muted">Poll the payment provider for the payout outcome. An unknown result stays pending until confirmed.</p>
                {checkPayoutMsg && <Banner tone="info">{checkPayoutMsg}</Banner>}
                <Button variant="primary" disabled={checkPayoutAction.pending} onClick={() => void checkPayoutAction.run()}>
                  {checkPayoutAction.pending ? 'Checking…' : 'Check Payout Status'}
                </Button>
              </section>
            )}

            {canFinalize && (
              <section className="card stack" aria-label="Finalize round">
                <SectionHead title="Finalize round" />
                <p className="muted">Run the final reconciliation audit. The round can only close when every check passes.</p>
                {finalizeMsg && <Banner tone="info">{finalizeMsg}</Banner>}
                <Button variant="primary" disabled={finalizeAction.pending} onClick={() => void finalizeAction.run()}>
                  {finalizeAction.pending ? 'Finalizing…' : 'Finalize Round'}
                </Button>
              </section>
            )}

            {!canApprove && !canPayout && !canCheckPayout && !canFinalize && <Banner tone="neutral" icon="lock">This screen is read-only. Approval and payout actions appear here when a settlement is awaiting approval or has been approved.</Banner>}
          </>
        )}
      </DataBoundary>
    </Screen>
  );
}
