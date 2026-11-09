'use client';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, Button, SectionHead, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { useApi, useSingleFlight } from '@/lib/hooks';
import { roleIn } from '@/lib/permissions';
import { sessionKey, useSession } from '@/lib/session';
import type { AgentMandateView, ProposedActionView } from '@/lib/types';

function mandateLabel(state: string) {
  switch (state) {
    case 'MANDATE_ISSUED': return 'Ready to execute';
    case 'EXECUTED': return 'Completed';
    case 'FAILED': return 'Failed';
    case 'EXPIRED': return 'Expired';
    case 'REVOKED': return 'Revoked';
    default: return state;
  }
}

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

function proposalLabel(state: string) {
  switch (state) {
    case 'PROPOSED': return 'Awaiting your approval';
    case 'APPROVED': return 'Approved';
    case 'REVOKED': return 'Revoked';
    default: return state;
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
  const [newKind, setNewKind] = useState('invoice');
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
      setApproveMsg('Approved — a single-use mandate has been issued.');
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
        rationale: 'Organizer-proposed agent action',
      });
      setCreateMsg('Proposal created — awaiting your approval.');
      setNewAmount('');
      setNewMemberId('');
    } catch (e) { setCreateMsg(describeError(e).message); }
  });

  return (
    <Screen title="Agent approvals">
      <DataBoundary state={circle}>
        {(c) => {
          const role = roleIn(c, ctx.actor);
          const isOrganizer = role === 'organizer';
          const pending = (proposals.data ?? []).filter((p) => p.state === 'PROPOSED');

          return (
            <>
              {!isOrganizer && (
                <Banner tone="neutral" icon="info">Only the circle organizer can approve, execute, or revoke mandates.</Banner>
              )}

              {circle.data && (
                <>
                  <section className="card stack" aria-label="Proposals awaiting approval">
                    <SectionHead title="Proposals awaiting your approval" />
                    <p className="muted">An agent has proposed these actions. Approving issues a single-use mandate that locks the exact amount and recipient.</p>
                    {pending.length === 0 ? (
                      <div className="state">
                        <p>No proposals waiting for your decision.</p>
                      </div>
                    ) : (
                      <ul>
                        {pending.map((p) => (
                          <li key={p.id} className="listrow">
                            <div className="grow">
                              <div style={{ fontWeight: 600 }}>{p.kind.charAt(0).toUpperCase() + p.kind.slice(1)}</div>
                              <div className="muted">{p.rationale ?? 'No reason recorded'}</div>
                              <div className="muted num" style={{ fontSize: 12 }}>
                                Member {String(p.params.member_id)} · {Number(p.params.amount_minor)} {String(p.params.currency)}
                              </div>
                            </div>
                            <StatusPill tone={proposalTone(p.state)}>{proposalLabel(p.state)}</StatusPill>
                            {isOrganizer && approveProposalId !== p.id && (
                              <Button variant="secondary" small onClick={() => { setApproveProposalId(p.id); }}>
                                Approve
                              </Button>
                            )}
                            {approveProposalId === p.id && (
                              <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void approveAction.run(p.id); }} noValidate>
                                <div className="field">
                                  <label htmlFor="step-up-method">Confirm your identity</label>
                                  <select id="step-up-method" value={stepUpMethod} onChange={(e) => setStepUpMethod(e.target.value)}>
                                    <option value="BIOMETRIC">Biometric</option>
                                    <option value="OTP">One-time code</option>
                                  </select>
                                </div>
                                {stepUpMethod === 'OTP' && (
                                  <div className="field">
                                    <label htmlFor="step-up-evidence">One-time code</label>
                                    <input id="step-up-evidence" value={stepUpEvidence} onChange={(e) => setStepUpEvidence(e.target.value)} placeholder="Enter the code sent to you" />
                                  </div>
                                )}
                                <div className="field">
                                  <label htmlFor="cap-minor">Spend cap (minor units, optional)</label>
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

                  {isOrganizer && (
                    <section className="card stack" aria-label="Propose a new agent action">
                      <SectionHead title="Propose a new agent action" />
                      <p className="muted">Propose an action for an agent to carry out. It will only execute after you approve it.</p>
                      <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void createProposalAction.run(); }} noValidate>
                        <div className="field">
                          <label htmlFor="new-kind">Action type</label>
                          <select id="new-kind" value={newKind} onChange={(e) => setNewKind(e.target.value)}>
                            <option value="invoice">Catch-up invoice</option>
                            <option value="refund">Refund of overpayment</option>
                            <option value="payout">Payout to member</option>
                          </select>
                        </div>
                        <div className="field">
                          <label htmlFor="new-member-id">Member ID</label>
                          <input id="new-member-id" value={newMemberId} onChange={(e) => setNewMemberId(e.target.value)} />
                        </div>
                        <div className="field">
                          <label htmlFor="new-amount">Amount</label>
                          <input id="new-amount" type="number" value={newAmount} onChange={(e) => setNewAmount(e.target.value)} placeholder="e.g. 4000 for ₹40.00" />
                        </div>
                        <Button block type="submit" disabled={createProposalAction.pending}>
                          {createProposalAction.pending ? 'Creating…' : 'Propose action'}
                        </Button>
                        {createMsg && <Banner tone="info">{createMsg}</Banner>}
                      </form>
                    </section>
                  )}

                  <section className="card stack" aria-label="Mandate history">
                    <SectionHead title="Mandate history" />
                    <p className="muted">Single-use mandates issued after your approval. Each mandate locks the exact amount, recipient, and circle.</p>
                    {(mandates.data ?? []).length === 0 ? (
                      <div className="state">
                        <p>No mandates yet. Approve a proposal to issue one.</p>
                      </div>
                    ) : (
                      <ul>
                        {(mandates.data ?? []).map((m) => (
                          <li key={m.id} className="listrow">
                            <div className="grow">
                              <div style={{ fontWeight: 600 }}>{m.kind.charAt(0).toUpperCase() + m.kind.slice(1)}</div>
                              <div className="muted">Mandate {m.id.slice(0, 8)}… · cap {m.cap_minor} {m.currency}</div>
                              <div className="muted num" style={{ fontSize: 12 }}>
                                Issued {new Date(m.created_at).toLocaleDateString()} · expires {new Date(m.expires_at).toLocaleDateString()}
                              </div>
                            </div>
                            <StatusPill tone={mandateTone(m.state)}>{mandateLabel(m.state)}</StatusPill>
                            {isOrganizer && m.state === 'MANDATE_ISSUED' && (
                              <Button variant="primary" small onClick={() => void executeAction.run(m.id)} disabled={executeAction.pending}>
                                {executeAction.pending ? 'Executing…' : 'Execute'}
                              </Button>
                            )}
                            {isOrganizer && m.state === 'MANDATE_ISSUED' && (
                              <Button variant="ghost" small onClick={() => { setRevokeReason(''); }} title="Revoke mandate">
                                Revoke
                              </Button>
                            )}
                            {m.state === 'FAILED' && m.outcome && (
                              <div className="muted" style={{ fontSize: 11 }}>{String(m.outcome.error ?? '')}</div>
                            )}
                            {m.state === 'EXECUTED' && m.outcome && (m.outcome.provider_ref as string) && (
                              <div className="muted" style={{ fontSize: 11 }}>Provider ref: {String(m.outcome.provider_ref)}</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {isOrganizer && (
                    <section className="card stack" aria-label="Revoke a mandate">
                      <SectionHead title="Revoke a mandate" />
                      <p className="muted">Revoke an issued mandate before it is executed or expires.</p>
                      <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void revokeAction.run(''); }} noValidate>
                        <div className="field">
                          <label htmlFor="revoke-reason">Reason</label>
                          <input id="revoke-reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} placeholder="Why revoke this mandate?" />
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <Button type="submit" variant="secondary" disabled={revokeAction.pending}>
                            {revokeAction.pending ? 'Revoking…' : 'Revoke mandate'}
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
