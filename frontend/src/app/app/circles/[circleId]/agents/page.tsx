'use client';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Amount, Banner, Button, Card, EmptyState, Field, KeyValue, Modal, Pill, Skeleton, Tabs } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { circleHref } from '@/lib/routes';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAction, useApi } from '@/lib/hooks';
import { sessionKey, useSession } from '@/lib/session';
import { humanize } from '@/lib/status';
import { useToast } from '@/lib/toast';
import type { CircleView, ProposedActionView } from '@/lib/types';

type TabId = 'review' | 'ready' | 'history';

const KIND: Record<string, { title: string; tier: string; icon: 'send' | 'receipt' | 'arrowUp' }> = {
  reminder: { title: 'Send a reminder', tier: 'Tier 0 · message only, no money moves', icon: 'send' },
  invoice: { title: 'Send a catch-up invoice', tier: 'Tier 1 · requests a payment through PayPal', icon: 'receipt' },
  payout: { title: 'Release a payout', tier: 'Tier 2 · moves money to the recipient', icon: 'arrowUp' },
};

export default function AgentsPage() {
  const { circleId } = useParams<{ circleId: string }>();
  const session = useSession();
  const toast = useToast();
  const key = sessionKey(session);
  const circle = useApi(`circle:${key}:${circleId}`, (s) => api.getCircle(session, circleId, s));
  const proposals = useApi(`proposals:${key}:${circleId}`, (s) => api.listProposals(session, circleId, s));
  const [tab, setTab] = useState<TabId>('review');
  const run = useAction(async () => {
    const r = await api.runCollectionsAgent(session, circleId);
    toast(r.created.length ? `Collections agent proposed ${r.created.length} action${r.created.length === 1 ? '' : 's'}` : 'Nothing new to propose', r.created.length ? 'success' : 'info');
    proposals.refetch();
    return r;
  });

  return (
    <DataBoundary state={circle} skeleton={<div className="page"><Skeleton count={3} /></div>}>
      {(c) => (
        <Screen title="Approvals" back={{ href: circleHref(c.id), label: c.name }}
          subtitle="Agents propose. You approve with step-up verification. Only then can the action run, exactly once."
          actions={<Button icon="bot" disabled={run.pending} onClick={() => void run.run()}>{run.pending ? 'Scanning…' : 'Run collections agent'}</Button>}>
          {run.error && <Banner tone="danger">{run.error}</Banner>}
          <DataBoundary state={proposals} skeleton={<Skeleton count={2} />}>
            {(list) => {
              const review = list.filter((p) => p.state === 'PROPOSED');
              const ready = list.filter((p) => p.state === 'APPROVED' && p.mandate?.state === 'MANDATE_ISSUED');
              const history = list.filter((p) => !review.includes(p) && !ready.includes(p));
              const shown = tab === 'review' ? review : tab === 'ready' ? ready : history;
              return (
                <>
                  <Tabs label="Proposal queue" value={tab} onChange={setTab} tabs={[
                    { id: 'review', label: 'To review', count: review.length },
                    { id: 'ready', label: 'Approved · ready', count: ready.length },
                    { id: 'history', label: 'History' },
                  ]} />
                  {shown.length === 0 ? (
                    <Card>
                      <EmptyState icon="bot" title={tab === 'review' ? 'Nothing to review' : tab === 'ready' ? 'Nothing waiting to run' : 'No history yet'}>
                        {tab === 'review'
                          ? 'Run the collections agent to check who owes money. It follows a fixed schedule: a heads-up before the due date, a friendly reminder, a follow-up, then a catch-up invoice after 7 days.'
                          : tab === 'ready' ? 'Approved actions appear here until they run or their mandate expires.' : 'Executed, rejected and expired actions are kept here as an audit trail.'}
                      </EmptyState>
                    </Card>
                  ) : (
                    <div className="grid grid--2">
                      {shown.map((p) => <ProposalCard key={p.id} p={p} c={c} onChanged={proposals.refetch} />)}
                    </div>
                  )}
                </>
              );
            }}
          </DataBoundary>
          <Banner tone="neutral" icon="shield">
            Guardrails: amounts and recipients come only from the stored proposal; the server re-checks the member’s
            outstanding balance at execution and refuses if anything changed. Each mandate is single-use and expires in 30 minutes.
          </Banner>
        </Screen>
      )}
    </DataBoundary>
  );
}

function ProposalCard({ p, c, onChanged }: { p: ProposedActionView; c: CircleView; onChanged: () => void }) {
  const session = useSession();
  const toast = useToast();
  const k = KIND[p.kind] ?? { title: humanize(p.kind), tier: '', icon: 'receipt' as const };
  const name = p.params.member_name ?? c.members.find((m) => m.id === p.params.member_id)?.name ?? 'Member';
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const act = useAction(async (fn: () => Promise<string>) => {
    try { toast(await fn()); } finally { onChanged(); }      // a failed run still consumes the mandate
  });
  const mandate = p.mandate;
  const outcome = mandate?.outcome as Record<string, string> | null | undefined;

  return (
    <Card className="proposal"
      title={<span className="row"><span className="glyph glyph--brand"><Icon name={k.icon} /></span>{k.title}</span>}
      subtitle={k.tier}
      action={<Pill tone={p.state === 'PROPOSED' ? 'warning' : p.state === 'REJECTED' ? 'neutral' : mandate?.state === 'EXECUTED' ? 'success' : mandate?.state === 'FAILED' ? 'danger' : 'brand'}>
        {mandate ? humanize(mandate.state) : humanize(p.state)}</Pill>}>
      <KeyValue rows={[
        ['Member', name],
        ['Amount', <Amount key="a" minor={p.params.amount_minor} currency={p.params.currency} />],
        ['Round', p.params.cycle_number ? `Round ${p.params.cycle_number}${p.params.due_date ? ` · due ${formatDate(p.params.due_date, true)}` : ''}` : '—'],
      ]} />
      {p.rationale && <p className="small">{p.rationale}</p>}
      {p.params.message && <blockquote>{p.params.message}</blockquote>}
      <p className="muted small">Proposed by {p.proposed_by.replace('agent:', '')} agent · {formatDateTime(p.created_at)}</p>

      {p.state === 'PROPOSED' && (
        <div className="row row--wrap">
          <Button icon="shield" onClick={() => setApproving(true)}>Approve with verification</Button>
          <Button variant="ghost" onClick={() => setRejecting(true)}>Dismiss</Button>
        </div>
      )}
      {mandate?.state === 'MANDATE_ISSUED' && (
        <div className="stack stack--sm">
          <p className="muted small">Mandate expires {formatDateTime(mandate.expires_at)} · cap <Amount minor={mandate.cap_minor} currency={p.params.currency} /></p>
          <div className="row row--wrap">
            <Button icon="play" disabled={act.pending} onClick={() => void act.run(async () => {
              await api.executeMandate(session, mandate.id);
              return p.kind === 'invoice' ? 'Catch-up invoice created' : p.kind === 'reminder' ? 'Reminder sent' : 'Action executed';
            })}>Run now</Button>
            <Button variant="ghost" disabled={act.pending} onClick={() => void act.run(async () => {
              await api.revokeMandate(session, mandate.id, 'revoked by organizer'); return 'Mandate revoked';
            })}>Revoke</Button>
          </div>
        </div>
      )}
      {outcome && mandate?.state === 'EXECUTED' && (
        <Banner tone="success">
          {p.kind === 'invoice' ? <>Invoice {outcome.provider_ref} created.{' '}
            {outcome.approval_url && <a className="link" href={outcome.approval_url} target="_blank" rel="noreferrer">Open payment link <Icon name="external" /></a>}</>
            : p.kind === 'reminder' ? 'Reminder delivered in the app.' : `Provider status: ${outcome.status}`}
        </Banner>
      )}
      {outcome && (mandate?.state === 'FAILED' || mandate?.state === 'REVOKED') && (
        <Banner tone={mandate.state === 'FAILED' ? 'danger' : 'neutral'}>{outcome.error ? humanize(String(outcome.error)) : outcome.reason || 'Revoked'}</Banner>
      )}
      {act.error && <Banner tone="danger">{act.error}</Banner>}

      <StepUpModal open={approving} onClose={() => setApproving(false)} p={p} name={name} onDone={onChanged} />
      <Modal open={rejecting} title="Dismiss this proposal?" onClose={() => setRejecting(false)} footer={<>
        <Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
        <Button variant="danger" disabled={act.pending} onClick={() => void act.run(async () => {
          await api.rejectProposal(session, p.id, 'dismissed by organizer'); setRejecting(false); return 'Proposal dismissed';
        })}>Dismiss</Button>
      </>}>
        <p>No mandate will be issued and nothing will run. The agent may propose again on a later run if the balance is still open.</p>
      </Modal>
    </Card>
  );
}

/**
 * Step-up confirmation. In this build the code is a local confirmation step (sandbox); production wires it to
 * OTP / device biometrics. The server records the method used with the mandate.
 */
function StepUpModal({ open, onClose, p, name, onDone }: {
  open: boolean; onClose: () => void; p: ProposedActionView; name: string; onDone: () => void;
}) {
  const session = useSession();
  const toast = useToast();
  const [challenge] = useState(() => String(Math.floor(100000 + Math.random() * 900000)));
  const [code, setCode] = useState('');
  const approve = useAction(async () => {
    if (code !== challenge) throw new Error('That code doesn’t match. Type the 6 digits shown.');
    const m = await api.approveProposal(session, p.id, 'OTP', { confirmed_at: new Date().toISOString(), channel: 'in_app_sandbox' });
    toast(`Approved. Mandate valid until ${formatDateTime(m.expires_at)}`);
    setCode(''); onClose(); onDone();
  });
  return (
    <Modal open={open} title="Confirm it’s you" onClose={onClose} footer={<>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button icon="shield" disabled={code.length !== 6 || approve.pending} onClick={() => void approve.run()}>{approve.pending ? 'Approving…' : 'Approve'}</Button>
    </>}>
      <p>You are approving <b>{KIND[p.kind]?.title.toLowerCase() ?? p.kind}</b> for <b>{name}</b> of{' '}
        <Amount minor={p.params.amount_minor} currency={p.params.currency} />. This issues a single-use mandate locked to exactly these details.</p>
      <Banner tone="info" icon="lock">Verification code (sandbox): <b className="mono" style={{ fontSize: 15 }}>{challenge}</b></Banner>
      <Field label="Enter the 6-digit code">
        {(id) => <input id={id} className="otp" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />}
      </Field>
      {approve.error && <Banner tone="danger">{approve.error}</Banner>}
    </Modal>
  );
}
