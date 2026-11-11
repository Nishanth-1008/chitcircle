'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/Icon';
import { DataBoundary, FinancialBreakdown, RoundStepper, StateBadge } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Amount, Banner, Button, Card, Field, KeyValue, Modal, Pill, Skeleton } from '@/components/ui';
import { useAppConfig } from '@/lib/appConfig';
import { api } from '@/lib/api/endpoints';
import { circleCycleHref, settlementHref, settlementReconciliationHref } from '@/lib/routes';
import { formatDateTime } from '@/lib/format';
import { useAction, useApi } from '@/lib/hooks';
import { sessionKey, useSession } from '@/lib/session';
import { SECURITY_INFO, humanize, stateInfo } from '@/lib/status';
import { useToast } from '@/lib/toast';
import type { CircleView, SettlementView } from '@/lib/types';
import { ACTIVE_POLL_STATES } from '@/lib/workflow';

export default function SettlementPage() {
  const { settlementId } = useParams<{ settlementId: string }>();
  const session = useSession();
  const key = sessionKey(session);
  const [poll, setPoll] = useState(false);
  const st = useApi(`settlement:${key}:${settlementId}`, (s) => api.getSettlement(session, settlementId, s), { pollMs: poll ? 4000 : 20000 });
  const circleId = st.data?.circle_id;
  const circle = useApi(circleId ? `circle:${key}:${circleId}` : null, (s) => api.getCircle(session, circleId!, s));
  useEffect(() => { setPoll(!!st.data && ACTIVE_POLL_STATES.includes(st.data.cycle_state)); }, [st.data]);

  return (
    <DataBoundary state={st} skeleton={<div className="page"><Skeleton count={3} /></div>}>
      {(s) => (
        <DataBoundary state={circle} skeleton={<div className="page"><Skeleton count={3} /></div>}>
          {(c) => <SettlementBody s={s} c={c} onChanged={() => { st.refetch(); circle.refetch(); }} />}
        </DataBoundary>
      )}
    </DataBoundary>
  );
}

function SettlementBody({ s, c, onChanged }: { s: SettlementView; c: CircleView; onChanged: () => void }) {
  const nameOf = (id: string) => c.members.find((m) => m.id === id)?.name ?? 'Member';
  const roundHref = circleCycleHref(c.id, s.cycle_id);
  return (
    <Screen
      wide
      title={`Settlement · Round ${s.cycle_number}`}
      back={{ href: roundHref, label: `${c.name} · Round ${s.cycle_number}` }}
      subtitle={<><StateBadge state={s.cycle_state} /><span>Recipient: <b>{nameOf(s.settlement.winner_member_id)}</b></span>
        <span>Rules v{s.ruleset_version}</span></>}
    >
      <Card><RoundStepper state={s.cycle_state} priorState={s.prior_state} /></Card>
      <Actions s={s} c={c} nameOf={nameOf} onChanged={onChanged} />
      <FinancialBreakdown data={s.settlement} myMemberId={c.my_member_id} nameOf={nameOf} />
      <div className="grid grid--2">
        <Card title="Approvals" subtitle={`${s.approvals.filter((a) => a.decision === 'APPROVE').length} of ${s.required_approvals} required`}>
          {s.approvals.length === 0 ? <p className="muted">No decisions recorded yet.</p> : (
            <ul className="list">
              {s.approvals.map((a, i) => (
                <li key={i} className="list__row">
                  <span className={`glyph glyph--${a.decision === 'APPROVE' ? 'income' : 'danger'}`}><Icon name={a.decision === 'APPROVE' ? 'check' : 'x'} /></span>
                  <div className="grow">
                    <div className="list__title">{a.approver_id === c.organizer_id ? 'Organizer' : 'Approver'} {a.decision === 'APPROVE' ? 'approved' : 'rejected'}</div>
                    <div className="muted small">{formatDateTime(a.created_at)}{a.reason ? ` · ${a.reason}` : ''}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Payout record">
          <KeyValue rows={[
            ['Amount', <Amount key="a" minor={s.settlement.winner_payout.minor} currency={s.settlement.currency} />],
            ['Requested', s.payout_requested_at ? formatDateTime(s.payout_requested_at) : 'Not yet'],
            ['Provider reference', s.provider_payout_ref ? <span key="p" className="mono">{s.provider_payout_ref}</span> : 'None yet'],
            ['Idempotency key', <span key="k" className="mono">{s.payout_reference}</span>],
            ['Finalized', s.finalized_at ? formatDateTime(s.finalized_at) : 'Not yet'],
          ]} />
          <Link className="link" href={settlementReconciliationHref(s.id)}>Reconciliation report <Icon name="chevronRight" /></Link>
        </Card>
      </div>
      <p className="muted small">Every amount above comes from the stored settlement (rules fingerprint <span className="mono">{s.settlement.ruleset_fingerprint.slice(0, 16)}…</span>). The app never recalculates money.</p>
    </Screen>
  );
}

function Actions({ s, c, nameOf, onChanged }: { s: SettlementView; c: CircleView; nameOf: (id: string) => string; onChanged: () => void }) {
  const session = useSession();
  const toast = useToast();
  const config = useAppConfig();
  const org = c.my_role === 'organizer';
  const isApprover = session.user?.role === 'approver';
  const winnerIsMe = s.settlement.winner_member_id === c.my_member_id;
  const [decision, setDecision] = useState<'APPROVE' | 'REJECT' | null>(null);
  const [reason, setReason] = useState('');
  const act = useAction(async (fn: () => Promise<string>) => {
    try { toast(await fn()); } finally { onChanged(); }      // a failed payout still changes server state
  });
  const blocked = act.error;

  const approve = useAction(async () => {
    const r = await api.approveSettlement(session, s.id, decision!, reason.trim() || undefined);
    toast(decision === 'APPROVE' ? (r.cycle_state === 'APPROVED' ? 'Settlement approved' : 'Approval recorded') : 'Settlement rejected — round on hold', decision === 'APPROVE' ? 'success' : 'info');
    setDecision(null); setReason(''); onChanged();
  });

  const releasePayout = async () => {
    const r = await api.executePayout(session, s.id);
    if (r.outcome === 'HELD') throw new Error(`Payout held: ${(r.reasons ?? []).map(humanize).join(', ')}`);
    if (r.outcome === 'FAILED') throw new Error(`The provider rejected the payout: ${r.detail ?? 'unknown reason'}`);
    if (r.outcome === 'UNRESOLVED') return 'The provider hasn’t answered yet — check the payout status shortly';
    return r.detail ? `Payout submitted — ${r.detail}` : `Payout submitted (${config?.payment_gateway === 'paypal' ? 'PayPal' : 'mock gateway'})`;
  };

  const state = s.cycle_state;
  const info = stateInfo(state);
  const alreadyDecided = s.approvals.some((a) => a.approver_id === session.user?.id);
  const securityBlocks = s.require_security && s.winner_security_status !== 'VERIFIED';
  let content: ReactNode = null;

  if (state === 'AWAITING_APPROVAL') {
    if ((org || isApprover) && !winnerIsMe && !alreadyDecided) {
      content = (
        <>
          <p>Check the breakdown below, then record your decision. Approving does not move money; the payout is a separate step.</p>
          <div className="next-step__actions">
            <Button icon="check" onClick={() => setDecision('APPROVE')}>Approve settlement</Button>
            <Button variant="danger" icon="x" onClick={() => setDecision('REJECT')}>Reject</Button>
          </div>
        </>
      );
    } else if (winnerIsMe) {
      content = <p>You are this round’s recipient, so you can’t approve your own payout. {org ? 'A designated approver must approve it.' : ''}</p>;
    } else if (alreadyDecided) {
      content = <p>Your decision is recorded. Waiting for {s.required_approvals - s.approvals.filter((a) => a.decision === 'APPROVE').length} more approval(s).</p>;
    } else {
      content = <p>{info.hint}</p>;
    }
  } else if (state === 'APPROVED') {
    content = org ? (
      <>
        <p>Release the payout of <Amount minor={s.settlement.winner_payout.minor} currency={s.settlement.currency} /> to {nameOf(s.settlement.winner_member_id)}.
          The request is recorded before the provider is called, and the same idempotency key prevents a double payout.</p>
        {securityBlocks && <Banner tone="warning" title="Security not verified">
          The rules require verified security for the recipient (currently: {SECURITY_INFO[s.winner_security_status ?? 'NONE']?.label}). The payout will be held. Update it under the circle’s Members tab.</Banner>}
        <div className="next-step__actions">
          <Button icon="arrowUp" disabled={act.pending} onClick={() => void act.run(releasePayout)}>Release payout</Button>
        </div>
      </>
    ) : <p>{info.hint}</p>;
  } else if (state === 'PAYOUT_PENDING' || state === 'PAYOUT_SUBMITTED') {
    content = org ? (
      <>
        <p>The payout was sent to the provider. It is not confirmed until the provider says so, via its webhook or a status check.</p>
        <div className="next-step__actions">
          <Button variant="secondary" icon="refresh" disabled={act.pending} onClick={() => void act.run(async () => {
            const r = await api.checkPayout(session, s.id);
            return r.note ? `Provider: ${humanize(r.outcome)} — ${r.note}` : `Provider status: ${humanize(r.outcome)}`;
          })}>Check payout status</Button>
          {state === 'PAYOUT_PENDING' && <Button variant="secondary" icon="arrowUp" disabled={act.pending}
            onClick={() => void act.run(releasePayout)}>Retry submission</Button>}
          {config?.sandbox_tools && <Button icon="check" disabled={act.pending} onClick={() => void act.run(async () => {
            await api.sandboxPayout(session, s.id, 'COMPLETED');
            return 'Provider confirmation recorded (sandbox)';
          })}>Simulate provider confirmation</Button>}
        </div>
      </>
    ) : <p>{info.hint}</p>;
  } else if (state === 'PAYOUT_CONFIRMED' || state === 'RECONCILIATION_PENDING') {
    content = org ? (
      <>
        <p>The provider confirmed the payout. Finalizing runs a three-way reconciliation (payments, payout, ledger) and closes the round only if everything matches.</p>
        <div className="next-step__actions">
          <Button icon="checkCircle" disabled={act.pending} onClick={() => void act.run(async () => {
            await api.finalize(session, s.id); return 'Round finalized';
          })}>Finalize round</Button>
          <Link className="btn btn--secondary" href={settlementReconciliationHref(s.id)}>View reconciliation</Link>
        </div>
      </>
    ) : <p>{info.hint}</p>;
  } else if (state === 'FINALIZED') {
    content = <Banner tone="success" title="Round closed">The payout was confirmed, every check passed and the record is sealed.</Banner>;
  } else if (state === 'ON_HOLD' || state === 'FAILED' || state === 'DISPUTED') {
    content = (
      <>
        <p>{info.hint}</p>
        {s.state_reason && <Banner tone={state === 'DISPUTED' ? 'warning' : 'danger'} title="Recorded reason">{s.state_reason}</Banner>}
        {org && <div className="next-step__actions">
          <Link className="btn btn--primary" href={circleCycleHref(c.id, s.cycle_id)}>
            {state === 'DISPUTED' ? 'Resolve on the round page' : 'Review and resume the round'}</Link>
        </div>}
      </>
    );
  } else {
    content = <p>{info.hint}</p>;
  }

  return (
    <Card className="next-step" title={<span className="row"><Icon name="sparkles" width={18} height={18} /> {info.settlementLabel}</span>}
          action={<Pill tone={info.tone}>{info.label}</Pill>}>
      {content}
      {blocked && (
        <Banner tone="danger" title="That didn’t go through">
          {blocked}{' '}
          {state === ‘RECONCILIATION_PENDING’ && <Link className="link" href={settlementReconciliationHref(s.id)}>See what doesn’t match</Link>}
        </Banner>
      )}
      <Modal open={!!decision} title={decision === 'APPROVE' ? 'Approve settlement' : 'Reject settlement'} onClose={() => setDecision(null)}
        footer={<>
          <Button variant="ghost" onClick={() => setDecision(null)}>Cancel</Button>
          <Button variant={decision === 'REJECT' ? 'danger' : 'primary'} disabled={approve.pending || (decision === 'REJECT' && !reason.trim())}
                  onClick={() => void approve.run()}>{approve.pending ? 'Saving…' : decision === 'APPROVE' ? 'Approve' : 'Reject'}</Button>
        </>}>
        <KeyValue rows={[
          ['Recipient', nameOf(s.settlement.winner_member_id)],
          ['Recipient receives', <Amount key="w" minor={s.settlement.winner_payout.minor} currency={s.settlement.currency} />],
          ['Organizer commission', <Amount key="f" minor={s.settlement.commission.minor} currency={s.settlement.currency} />],
          ['Dividend pool', <Amount key="p" minor={s.settlement.dividend_pool.minor} currency={s.settlement.currency} />],
        ]} />
        <Field label={decision === 'REJECT' ? 'Why are you rejecting it?' : 'Note (optional)'}>
          {(id) => <textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        {decision === 'REJECT' && <Banner tone="warning">Rejecting puts the round on hold until the organizer resumes it.</Banner>}
        {approve.error && <Banner tone="danger">{approve.error}</Banner>}
      </Modal>
    </Card>
  );
}
