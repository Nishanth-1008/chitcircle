'use client';
import { useParams } from 'next/navigation';
import { DataBoundary } from '@/components/domain';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Banner, Button, Card, Pill, Skeleton } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { settlementHref } from '@/lib/routes';
import { useApi } from '@/lib/hooks';
import { reconcileLabel } from '@/lib/reconcile';
import { sessionKey, useSession } from '@/lib/session';
import type { DiscrepancyView, PartReport } from '@/lib/types';

export default function ReconciliationPage() {
  const { settlementId } = useParams<{ settlementId: string }>();
  const session = useSession();
  const key = sessionKey(session);
  const st = useApi(`settlement:${key}:${settlementId}`, (s) => api.getSettlement(session, settlementId, s));
  const rep = useApi(`recon:${key}:${settlementId}`, (s) => api.reconciliation(session, settlementId, s));
  const circleId = st.data?.circle_id;
  const circle = useApi(circleId ? `circle:${key}:${circleId}` : null, (s) => api.getCircle(session, circleId!, s));
  const nameOf = (id: string | null) => (id && circle.data?.members.find((m) => m.id === id)?.name) || 'Member';

  return (
    <Screen
      title="Reconciliation"
      back={{ href: settlementHref(settlementId), label: st.data ? `Settlement · Round ${st.data.cycle_number}` : 'Settlement' }}
      subtitle="Payments, the payout and the ledger checked against each other. A round finalizes only when all three are clean."
      actions={<Button variant="secondary" small icon="refresh" onClick={() => { rep.refetch(); st.refetch(); }}>Re-run checks</Button>}
    >
      <DataBoundary state={rep} skeleton={<Skeleton count={3} />}>
        {(r) => (
          <>
            {r.is_clean
              ? <Banner tone="success" title="Everything reconciles">Confirmed payments match obligations, the payout matches the settlement, and every journal balances.</Banner>
              : <Banner tone="warning" title="Something doesn’t line up yet">The round can be finalized only when every section below is clear.</Banner>}
            <div className="grid grid--3">
              <Part title="Member payments" icon="wallet" part={r.payments} nameOf={nameOf}
                    clean="Every member’s confirmed payments match their net installment." />
              <Part title="Recipient payout" icon="arrowUp" part={r.payout} nameOf={nameOf}
                    clean="The provider-confirmed payout matches the settlement exactly." />
              <Card title={<span className="row"><Icon name="scale" width={18} height={18} /> Ledger checks</span>}
                    action={<Pill tone={r.ledger_problems.length ? 'danger' : 'success'}>{r.ledger_problems.length ? 'Problems' : 'Balanced'}</Pill>}>
                {r.ledger_problems.length === 0
                  ? <p className="muted">All journals balance and the circle pool nets to zero.</p>
                  : <ul className="list">{r.ledger_problems.map((p, i) => (
                    <li key={i} className="list__row"><div className="grow"><div className="list__title">{reconcileLabel(p.code)}</div>
                      <div className="muted small">{p.member_id ? nameOf(p.member_id) : p.detail ?? p.event_id}</div></div></li>))}</ul>}
              </Card>
            </div>
          </>
        )}
      </DataBoundary>
    </Screen>
  );
}

function Part({ title, icon, part, nameOf, clean }: {
  title: string; icon: 'wallet' | 'arrowUp'; part: PartReport; nameOf: (id: string | null) => string; clean: string;
}) {
  const tone = part.is_clean ? 'success' : part.unresolved ? 'warning' : 'danger';
  const label = part.is_clean ? 'Matched' : part.unresolved ? 'Waiting' : 'Mismatch';
  return (
    <Card title={<span className="row"><Icon name={icon} width={18} height={18} /> {title}</span>} action={<Pill tone={tone}>{label}</Pill>}>
      {part.discrepancies.length === 0 ? <p className="muted">{part.unresolved ? 'Waiting for provider confirmation.' : clean}</p> : (
        <ul className="list">
          {part.discrepancies.map((d: DiscrepancyView, i) => (
            <li key={i} className="list__row">
              <div className="grow">
                <div className="list__title">{reconcileLabel(d.code)}</div>
                <div className="muted small">{d.member_id ? `${nameOf(d.member_id)} · ` : ''}{d.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
