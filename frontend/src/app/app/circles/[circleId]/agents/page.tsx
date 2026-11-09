'use client';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, Button, SectionHead, Skeleton, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { useApi, useSingleFlight } from '@/lib/hooks';
import { roleIn } from '@/lib/permissions';
import { sessionKey, useSession } from '@/lib/session';
import type { AgentMandateView, ProposedActionView } from '@/lib/types';

function mandateTone(state: string) {
  switch (state) {
    case 'MANDATE_ISSUED': return 'warning';
    case 'EXECUTED': return 'success';
    case 'FAILED': return 'danger';
    case 'EXPIRED': return 'neutral';
    case 'REVOKED': return 'neutral';
    default: return 'neutral';
  }
}

function proposalTone(state: string) {
  switch (state) {
    case 'PROPOSED': return 'warning';
    case 'APPROVED': return 'success';
    case 'REVOKED': return 'neutral';
    default: return 'neutral';
  }
}

export default function AgentsPage() {
  const { circleId } = useParams<{ circleId: string }>();
  const ctx = useSession();
  const k = sessionKey(ctx);
  const live = ctx.mode === 'live';

  const circle = useApi(`circle:${k}:${circleId}`, (s) => api.getCircle(ctx, circleId, s));
  const proposals = useApi<ProposedActionView[]>(`proposals:${k}:${circleId}`,
    (s) => api.listProposals(ctx, circleId, s));
  const mandates = useApi<AgentMandateView[]>(`mandates:${k}:${circleId}`,
    (s) => api.listMandates(ctx, circleId, s));

  const [approveMsg, setApproveMsg] = useState('');
  const [approveProposalId, setApproveProposalId] = useState('');
  const [stepUpMethod, setStepUpMethod] = useState('BIOMETRIC');
  const [stepUpEvidence, setStepUpEvidence] = useState('');
  const [capMinor, setCapMinor] = useState('');
  const [executeMsg, setExecuteMsg] = useState('');
  const [revokeMsg, setRevokeMsg] = useState('');
  const [revokeReason, setRevokeReason] = useState('');
  const [createMsg, setCreateMsg] = useState('');
  const [newKind, setNewKind] = useState('payout');
  const [newAmount, setNewAmount] = useState('');
  const [newMemberId, setNewMemberId] = useState('');

  const approveAction = useSingleFlight(async (proposalId: string) => {
    setApproveMsg('');
    const cap = capMinor ? Number(capMinor) : undefined;
    if (cap !== undefined && !Number.isFinite(cap)) { setApproveMsg('Cap must be a number.'); return; }
    try {
      await api.approveProposal(ctx, proposalId, {
        step_up_method: stepUpMethod,
        step_up_evidence: stepUpEvidence ? { note: stepUpEvidence } : undefined,
        ...(cap !== undefined ? { cap_minor: cap } : {}),
      });
      setApproveMsg('Proposal approved — mandate issued.');
      setApproveProposalId('');
      setStepUpMethod('BIOMETRIC');
      setStepUpEvidence('');
      setCapMinor('');
    } catch (e) { setApproveMsg(describeError(e).message); }
  });

  const executeAction = useSingleFlight(async (mandateId: string) => {
    setExecuteMsg('');
    try {
      const res = await api.executeMandate(ctx, mandateId);
      setExecuteMsg(`Mandate executed: ${JSON.stringify(res.outcome)}.`);
    } catch (e) { setExecuteMsg(describeError(e).message); }
  });

  const revokeAction = useSingleFlight(async (mandateId: string) => {
    setRevokeMsg('');
    try {
      await api.revokeMandate(ctx, mandateId, { reason: revokeReason || undefined });
      setRevokeMsg('Mandate revoked.');
      setRevokeReason('');
    } catch (e) { setRevokeMsg(describeError(e).message); }
  });

  const createProposalAction = useSingleFlight(async () => {
    setCreateMsg('');
    const amount = Number(newAmount);
    if (!Number.isFinite(amount) || amount <= 0) { setCreateMsg('Enter a valid amount.'); return; }
    if (!newMemberId.trim()) { setCreateMsg('Enter a member ID.'); return; }
    try {
      await api.createProposal(ctx, circleId, {
        kind: newKind,
        params: {
          member_id: newMemberId,
          amount_minor: Math.round(amount * 100),
          currency: 'INR',
          cycle_id: '',
        },
        rationale: 'Manual agent proposal',
      });
      setCreateMsg('Proposal created.');
      setNewAmount('');
      setNewMemberId('');
    } catch (e) { setCreateMsg(describeError(e).message); }
  });

  return (
    <Screen title="Agents & Mandates" back={`/app/circles/${encodeURIComponent(circleId)}`}>
      <DataBoundary state={circle}>
        {(c) => {
          const role = roleIn(c, ctx.actor);
          const isOrganizer = role === 'organizer';
          const pending = (proposals.data ?? []).filter((p) => p.state === 'PROPOSED');
          const issued = (mandates.data ?? []).filter((m) => m.state === 'MANDATE_ISSUED');

          return (
            <>
              {!live && <Banner tone="info">Demo mode — agent actions are simulated. No real provider calls are made.</Banner>}
              {!isOrganizer && <Banner tone="neutral">Only the organizer can approve, execute, or revoke mandates.</Banner>}

              {circle.data && (
                <>
                  <section className="card stack" aria-label="Proposal queue">
                    <SectionHead title="Agent Proposal Queue" />
                    <p className="muted">Proposals awaiting organizer approval. Approving issues a single-use, hash-locked mandate.</p>
                    {pending.length === 0 ? (
                      <p className="muted">No pending proposals.</p>
                    ) : (
                      <ul>
                        {pending.map((p) => (
                          <li key={p.id} className="listrow">
                            <div className="grow">
                              <div style={{ fontWeight: 600 }}>{p.kind}</div>
                              <div className="muted">{p.rationale ?? 'No rationale'}</div>
                              <div className="muted num" style={{ fontSize: 12 }}>
                                Member {String(p.params.member_id)} · {Number(p.params.amount_minor)} {String(p.params.currency)}
                              </div>
                            </div>
                            <StatusPill tone={proposalTone(p.state)}>{p.state}</StatusPill>
                            {isOrganizer && live && approveProposalId !== p.id && (
                              <Button variant="secondary" small onClick={() => { setApproveProposalId(p.id); }}>
                                Approve
                              </Button>
                            )}
                            {approveProposalId === p.id && (
                              <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void approveAction.run(p.id); }} noValidate>
                                <div className="field">
                                  <label htmlFor="step-up-method">Step-up method</label>
                                  <select id="step-up-method" value={stepUpMethod} onChange={(e) => setStepUpMethod(e.target.value)}>
                                    <option value="BIOMETRIC">Biometric</option>
                                    <option value="OTP">OTP</option>
                                  </select>
                                </div>
                                <div className="field">
                                  <label htmlFor="step-up-evidence">Evidence (optional)</label>
                                  <input id="step-up-evidence" value={stepUpEvidence} onChange={(e) => setStepUpEvidence(e.target.value)} placeholder="e.g. OTP code" />
                                </div>
                                <div className="field">
                                  <label htmlFor="cap-minor">Cap (minor units, optional)</label>
                                  <input id="cap-minor" type="number" value={capMinor} onChange={(e) => setCapMinor(e.target.value)} placeholder="Defaults to proposed amount" />
                                </div>
                                <div style={{ display: 'flex', gap: 8 }}>
                                  <Button type="submit" variant="primary" disabled={approveAction.pending}>
                                    {approveAction.pending ? 'Approving…' : 'Approve'}
                                  </Button>
                                  <Button variant="ghost" small onClick={() => setApproveProposalId('')}>Cancel</Button>
                                </div>
                                {approveMsg && <Banner tone="info">{approveMsg}</Banner>}
                              </form>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {isOrganizer && live && (
                    <section className="card stack" aria-label="Create proposal">
                      <SectionHead title="Create Agent Proposal" />
                      <p className="muted">Propose a mandate-gated action. A human must approve before anything executes.</p>
                      <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void createProposalAction.run(); }} noValidate>
                        <div className="field">
                          <label htmlFor="new-kind">Action kind</label>
                          <select id="new-kind" value={newKind} onChange={(e) => setNewKind(e.target.value)}>
                            <option value="payout">Payout</option>
                            <option value="invoice">Invoice</option>
                            <option value="refund">Refund</option>
                          </select>
                        </div>
                        <div className="field">
                          <label htmlFor="new-member-id">Member ID</label>
                          <input id="new-member-id" value={newMemberId} onChange={(e) => setNewMemberId(e.target.value)} />
                        </div>
                        <div className="field">
                          <label htmlFor="new-amount">Amount (major units)</label>
                          <input id="new-amount" type="number" value={newAmount} onChange={(e) => setNewAmount(e.target.value)} placeholder="e.g. 4000 for ₹40.00" />
                        </div>
                        <Button block type="submit" disabled={createProposalAction.pending}>
                          {createProposalAction.pending ? 'Creating…' : 'Create Proposal'}
                        </Button>
                        {createMsg && <Banner tone="info">{createMsg}</Banner>}
                      </form>
                    </section>
                  )}

                  <section className="card stack" aria-label="Mandate audit trail">
                    <SectionHead title="Mandates" />
                    <p className="muted">Single-use, hash-locked mandates issued after human approval.</p>
                    {(mandates.data ?? []).length === 0 ? (
                      <p className="muted">No mandates yet.</p>
                    ) : (
                      <ul>
                        {(mandates.data ?? []).map((m) => (
                          <li key={m.id} className="listrow">
                            <div className="grow">
                              <div style={{ fontWeight: 600 }}>{m.kind}</div>
                              <div className="muted">Mandate {m.id.slice(0, 8)}… · {m.currency} {m.cap_minor} cap</div>
                              <div className="muted num" style={{ fontSize: 12 }}>
                                Issued by {m.issued_by} · {new Date(m.expires_at).toLocaleString()} expiry
                              </div>
                            </div>
                            <StatusPill tone={mandateTone(m.state)}>{m.state}</StatusPill>
                            {isOrganizer && live && m.state === 'MANDATE_ISSUED' && (
                              <Button variant="primary" small onClick={() => void executeAction.run(m.id)} disabled={executeAction.pending}>
                                {executeAction.pending ? 'Executing…' : 'Execute'}
                              </Button>
                            )}
                            {isOrganizer && live && m.state === 'MANDATE_ISSUED' && (
                              <Button variant="ghost" small onClick={() => { setRevokeReason(''); }} title="Revoke">
                                Revoke
                              </Button>
                            )}
                            {m.state === 'FAILED' && m.outcome && (
                              <div className="muted" style={{ fontSize: 11 }}>{String(m.outcome.error ?? '')}</div>
                            )}
                            {m.state === 'EXECUTED' && m.outcome && (
                              <div className="muted" style={{ fontSize: 11 }}>Provider: {String(m.outcome.provider_ref ?? '')}</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {isOrganizer && live && (
                    <section className="card stack" aria-label="Revoke mandate">
                      <SectionHead title="Revoke Mandate" />
                      <p className="muted">Revoke an unused (MANDATE_ISSUED) mandate before it is executed or expires.</p>
                      <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void revokeAction.run(''); }} noValidate>
                        <div className="field">
                          <label htmlFor="revoke-reason">Reason</label>
                          <input id="revoke-reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} placeholder="Why revoke?" />
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <Button type="submit" variant="secondary" disabled={revokeAction.pending}>
                            {revokeAction.pending ? 'Revoking…' : 'Revoke Selected'}
                          </Button>
                        </div>
                        {revokeMsg && <Banner tone="info">{revokeMsg}</Banner>}
                      </form>
                    </section>
                  )}

                  {executeMsg && <Banner tone="info">{executeMsg}</Banner>}
                  {revokeMsg && <Banner tone="info">{revokeMsg}</Banner>}
                </>
              )}
            </>
          );
        }}
      </DataBoundary>
    </Screen>
  );
}
