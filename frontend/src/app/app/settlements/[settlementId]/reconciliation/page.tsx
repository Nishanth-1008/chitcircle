'use client';
import { useParams } from 'next/navigation';
import { DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, Skeleton, StatusPill } from '@/components/ui';
import { Icon } from '@/components/Icon';
import { api } from '@/lib/api/endpoints';
import { useApi } from '@/lib/hooks';
import { reconcileLabel } from '@/lib/reconcile';
import { sessionKey, useSession } from '@/lib/session';
import type { PartReport } from '@/lib/types';

function Part({ title, report, unresolvedText, nameOf }: { title: string; report: PartReport; unresolvedText: string; nameOf: (id: string | null) => string | null }) {
  const clean = report.is_clean;
  return (
    <section className="card stack" aria-label={title}>
      <div className="row row--between">
        <h3>{title}</h3>
        <StatusPill tone={clean ? 'success' : report.unresolved && report.discrepancies.length === 0 ? 'warning' : 'danger'} icon={clean ? 'check' : 'alert'}>
          {clean ? 'Matches' : report.unresolved && report.discrepancies.length === 0 ? 'Waiting' : 'Needs attention'}
        </StatusPill>
      </div>
      {report.unresolved && <p className="muted">{unresolvedText}</p>}
      {report.discrepancies.length > 0 && (
        <ul>
          {report.discrepancies.map((d, i) => (
            <li key={i} className="listrow">
              <Icon name="alert" width={18} height={18} />
              <div className="grow">
                <div style={{ fontWeight: 600 }}>{reconcileLabel(d.code)}</div>
                <div className="muted">{nameOf(d.member_id) ?? 'Circle-wide'} · <span className="num">{d.detail}</span></div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {clean && !report.unresolved && <p className="muted">Nothing to resolve.</p>}
    </section>
  );
}

export default function ReconciliationPage() {
  const { settlementId } = useParams<{ settlementId: string }>();
  const ctx = useSession();
  const k = sessionKey(ctx);
  const recon = useApi(`recon:${k}:${settlementId}`, (s) => api.getReconciliation(ctx, settlementId, s));
  const settlement = useApi(`settlement:${k}:${settlementId}`, (s) => api.getSettlement(ctx, settlementId, s));
  const circleId = settlement.data?.settlement.circle_id ?? null;
  const circle = useApi(circleId ? `circle:${k}:${circleId}` : null, (s) => api.getCircle(ctx, circleId!, s));
  const nameOf = (id: string | null) => (id ? circle.data?.members.find((m) => m.id === id)?.name ?? `Member ${id.slice(0, 6)}` : null);

  return (
    <Screen title="Reconciliation" back={`/app/settlements/${encodeURIComponent(settlementId)}`}>
      <DataBoundary state={recon} skeleton={<Skeleton count={3} />}>
        {(r) => (
          <>
            <section className="card card--soft stack">
              <StatusPill tone={r.is_clean ? 'success' : 'warning'} icon={r.is_clean ? 'checkCircle' : 'alert'}>
                {r.is_clean ? 'Reconciled' : 'Reconciliation required'}
              </StatusPill>
              <p>{r.is_clean
                ? 'Payments, payout and ledger agree with each other.'
                : 'Something doesn’t line up yet. A round can be finalized only when everything below is clear.'}</p>
            </section>
            <Part title="Member payments" report={r.payments} nameOf={nameOf}
                  unresolvedText="Some provider payments are still pending." />
            <Part title="Winner payout" report={r.payout} nameOf={nameOf}
                  unresolvedText="No provider-confirmed payout yet. An unknown outcome stays unresolved." />
            <section className="card stack" aria-label="Ledger checks">
              <div className="row row--between">
                <h3>Ledger checks</h3>
                <StatusPill tone={r.ledger_problems.length === 0 ? 'success' : 'danger'}>{r.ledger_problems.length === 0 ? 'Balanced' : 'Needs attention'}</StatusPill>
              </div>
              {r.ledger_problems.length === 0
                ? <p className="muted">All journals balance and the circle pool nets to zero.</p>
                : <ul>{r.ledger_problems.map((p, i) => (
                    <li key={i} className="listrow"><Icon name="alert" width={18} height={18} />
                      <div className="grow"><div style={{ fontWeight: 600 }}>{reconcileLabel(p.code)}</div>
                        <div className="muted">{p.member_id ? nameOf(p.member_id) : p.event_id ?? p.detail ?? ''}</div></div></li>))}</ul>}
            </section>
            <Banner tone="neutral" icon="lock">Read-only. Finalizing a settlement is a server action that succeeds only when every check passes.</Banner>
          </>
        )}
      </DataBoundary>
    </Screen>
  );
}
