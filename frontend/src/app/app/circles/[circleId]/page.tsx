'use client';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { DataBoundary, StateBadge } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Avatar, Banner, Button, EmptyState, FilterTabs, StatusPill } from '@/components/ui';
import { Icon } from '@/components/Icon';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { formatDate, shortId } from '@/lib/format';
import { useApi, useSingleFlight } from '@/lib/hooks';
import { canViewMemberSecurity, roleIn } from '@/lib/permissions';
import { useSaved } from '@/lib/saved';
import { sessionKey, useSession } from '@/lib/session';
import { SECURITY_INFO } from '@/lib/status';

type Tab = 'overview' | 'members' | 'rules' | 'rounds';

function RoundRow({ circleId, roundId }: { circleId: string; roundId: string }) {
  const ctx = useSession();
  const round = useApi(`round-row:${sessionKey(ctx)}:${roundId}`, (s) => api.getCycle(ctx, roundId, s));
  const href = `/app/circles/${encodeURIComponent(circleId)}/cycles/${encodeURIComponent(roundId)}`;
  if (round.error && !round.data) {
    return (
      <li className="listrow"><div className="grow"><span className="num muted">{shortId(roundId, 12)}</span>
        <div className="field__error">{describeError(round.error).message}</div></div></li>
    );
  }
  return (
    <li>
      <Link href={href} className="listrow">
        <div className="grow">
          <div style={{ fontWeight: 600 }}>{round.data ? `Round ${round.data.number}` : 'Loading…'}</div>
          <div className="muted">{round.data ? `Due ${formatDate(round.data.due_date)}` : ' '}</div>
        </div>
        {round.data && <StateBadge state={round.data.state} />}
        <Icon name="chevronRight" width={18} height={18} />
      </Link>
    </li>
  );
}

export default function CircleDetailPage() {
  const { circleId } = useParams<{ circleId: string }>();
  const router = useRouter();
  const ctx = useSession();
  const saved = useSaved(ctx.mode);
  const [tab, setTab] = useState<Tab>('overview');
  const [roundId, setRoundId] = useState('');
  const [roundError, setRoundError] = useState('');

  const circle = useApi(`circle:${sessionKey(ctx)}:${circleId}`, (s) => api.getCircle(ctx, circleId, s));
  useEffect(() => { if (circle.data) saved.saveCircle(circle.data.id); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [circle.data?.id]);

  const open = useSingleFlight(async () => {
    const id = roundId.trim();
    if (!id) { setRoundError('Enter a round ID.'); return; }
    try {
      const cycle = await api.getCycle(ctx, id);
      if (cycle.circle_id !== circleId) { setRoundError('That round belongs to a different circle.'); return; }
      saved.saveRound(cycle.id, circleId);
      router.push(`/app/circles/${encodeURIComponent(circleId)}/cycles/${encodeURIComponent(cycle.id)}`);
    } catch (e) { setRoundError(describeError(e).message); }
  });

  const rounds = saved.items.rounds.filter((r) => r.circleId === circleId);

  return (
    <Screen title={circle.data?.name ?? 'Circle'} back="/app/circles">
      <DataBoundary state={circle}>
        {(c) => {
          const role = roleIn(c, ctx.actor);
          const active = c.rulesets.find((r) => r.status === 'ACTIVE');
          return (
            <>
              <div className="row row--between">
                <StatusPill tone={role === 'none' ? 'neutral' : 'brand'} icon={role === 'organizer' ? 'scale' : 'users'}>
                  {role === 'organizer' ? 'You organize this circle' : role === 'member' ? 'You’re a member' : 'You’re viewing this circle'}
                </StatusPill>
              </div>
              <FilterTabs label="Circle sections" value={tab} onChange={setTab} tabs={[
                { id: 'overview', label: 'Overview' }, { id: 'members', label: 'Members' },
                { id: 'rules', label: 'Rules' }, { id: 'rounds', label: 'Rounds' },
              ]} />

              {tab === 'overview' && (
                <>
                  <section className="card stack" aria-label="Summary">
                    <div className="stats stats--2">
                      <div><div className="stat__label">Members</div><div className="stat__value num">{c.members.length}</div></div>
                      <div><div className="stat__label">Payouts received</div><div className="stat__value num">{c.members.filter((m) => m.has_won).length} of {c.members.length}</div></div>
                      <div><div className="stat__label">Active rule version</div><div className="stat__value num">{active ? `v${active.version}` : '—'}</div></div>
                      <div><div className="stat__label">Rounds on this device</div><div className="stat__value num">{rounds.length}</div></div>
                    </div>
                    <Banner tone="neutral" icon="info">
                      Chit value and installment terms aren’t returned by the circle endpoint yet. They appear on a round once the server provides them.
                    </Banner>
                  </section>
                  <section className="card stack" aria-label="Open a round">
                    <h3>Open a round</h3>
                    <form className="stack" onSubmit={(e) => { e.preventDefault(); void open.run(); }} noValidate>
                      <div className="field">
                        <label htmlFor="round-id">Round ID</label>
                        <input id="round-id" value={roundId} onChange={(e) => { setRoundId(e.target.value); setRoundError(''); }}
                               autoComplete="off" spellCheck={false} aria-invalid={!!roundError} aria-describedby="round-msg" />
                        <span id="round-msg" className={roundError ? 'field__error' : 'field__help'} role={roundError ? 'alert' : undefined}>
                          {roundError || 'The server doesn’t list rounds yet, so enter the ID you were given.'}
                        </span>
                      </div>
                      <Button type="submit" block variant="secondary" disabled={open.pending}>{open.pending ? 'Checking…' : 'Open round'}</Button>
                    </form>
                  </section>
                </>
              )}

              {tab === 'members' && (
                <section className="card" aria-label="Members">
                  <ul>
                    {c.members.map((m) => {
                      const sec = SECURITY_INFO[m.security_status] ?? SECURITY_INFO.NONE;
                      return (
                        <li key={m.id} className="listrow">
                          <Avatar name={m.name} />
                          <div className="grow">
                            <div style={{ fontWeight: 600 }}>{m.name}{m.id === ctx.actor?.id && <span className="muted"> (you)</span>}</div>
                            <div className="muted">Position {m.position}</div>
                          </div>
                          <div className="stack" style={{ gap: 4, alignItems: 'flex-end' }}>
                            {m.has_won && <StatusPill tone="success" icon="trophy">Received payout</StatusPill>}
                            {canViewMemberSecurity(role) && <StatusPill tone={sec.tone}>{sec.label}</StatusPill>}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}

              {tab === 'rules' && (
                <section className="card" aria-label="Rule versions">
                  <h3 style={{ marginBottom: 4 }}>Rule versions</h3>
                  <p className="muted" style={{ marginBottom: 8 }}>Each change creates a new version. Existing rounds keep the version they started with.</p>
                  <ul>
                    {c.rulesets.map((r) => (
                      <li key={r.version} className="listrow">
                        <div className="grow">
                          <div style={{ fontWeight: 600 }}>Version {r.version}</div>
                          <div className="muted">{r.reason ?? 'No reason recorded'}</div>
                          <div className="muted num" style={{ fontSize: 11 }} title={r.fingerprint}>Fingerprint {r.fingerprint.slice(0, 10)}…</div>
                        </div>
                        <StatusPill tone={r.status === 'ACTIVE' ? 'success' : 'neutral'}>{r.status === 'ACTIVE' ? 'Active' : r.status === 'SUPERSEDED' ? 'Replaced' : r.status}</StatusPill>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {tab === 'rounds' && (
                rounds.length === 0
                  ? <EmptyState icon="calendar" title="No rounds saved here" action={<Button variant="secondary" onClick={() => setTab('overview')}>Open a round</Button>}>
                      Open a round by its ID from the Overview tab.
                    </EmptyState>
                  : <section className="card" aria-label="Rounds"><ul>{rounds.map((r) => <RoundRow key={r.id} circleId={circleId} roundId={r.id} />)}</ul></section>
              )}
            </>
          );
        }}
      </DataBoundary>
    </Screen>
  );
}
