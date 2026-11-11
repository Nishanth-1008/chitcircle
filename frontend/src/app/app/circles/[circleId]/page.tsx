'use client';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/Icon';
import { DataBoundary, DueLine, RoleBadge, StateBadge } from '@/components/domain';
import { Screen } from '@/components/shell';
import {
  Amount, Avatar, Banner, Button, Card, EmptyState, Field, KeyValue, LinkButton, Modal, Pill, ProgressBar,
  Skeleton, Stat, Tabs,
} from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { activityHref, agentsHref, circleCycleHref, circleHref } from '@/lib/routes';
import { formatDate } from '@/lib/format';
import { useAction, useApi } from '@/lib/hooks';
import { describeRules, isAuction, payoutModeTitle } from '@/lib/ruleset';
import { sessionKey, useSession } from '@/lib/session';
import { SECURITY_INFO, humanize } from '@/lib/status';
import { useToast } from '@/lib/toast';
import type { CircleView, CycleSummary, MemberView, RiskView, TimelineView } from '@/lib/types';
import { paymentOpen } from '@/lib/workflow';

type TabId = 'overview' | 'rounds' | 'members' | 'timeline' | 'rules';

export default function CirclePage() {
  const { circleId } = useParams<{ circleId: string }>();
  const session = useSession();
  const key = sessionKey(session);
  const circle = useApi(`circle:${key}:${circleId}`, (s) => api.getCircle(session, circleId, s));
  const cycles = useApi(`cycles:${key}:${circleId}`, (s) => api.listCycles(session, circleId, s), { pollMs: 15000 });
  const [tab, setTab] = useState<TabId>('overview');
  const refresh = () => { circle.refetch(); cycles.refetch(); };

  return (
    <DataBoundary state={circle} skeleton={<div className="page"><Skeleton count={3} /></div>}>
      {(c) => (
        <Screen
          title={c.name}
          back={{ href: '/app/circles', label: 'Circles' }}
          subtitle={<>
            <RoleBadge role={c.my_role} />
            <span>{payoutModeTitle(c.ruleset.payout_mode)}</span>·
            <span>Pot <Amount minor={c.ruleset.total_chit_value} currency={c.currency} /></span>·
            <span>{c.members.length} members</span>
          </>}
          actions={<>
            <LinkButton href={activityHref(c.id)} variant="secondary" small icon="activity">Activity</LinkButton>
            {c.my_role === 'organizer' && <LinkButton href={agentsHref(c.id)} variant="soft" small icon="bot">Approvals</LinkButton>}
          </>}
        >
          <Tabs label="Circle sections" value={tab} onChange={setTab} tabs={[
            { id: 'overview', label: 'Overview' }, { id: 'rounds', label: 'Rounds' }, { id: 'members', label: 'Members' },
            { id: 'timeline', label: 'Timeline' }, { id: 'rules', label: 'Rules' },
          ]} />
          {tab === 'overview' && <Overview c={c} cycles={cycles.data} onChanged={refresh} />}
          {tab === 'rounds' && (
            <DataBoundary state={cycles}>{(list) => <Rounds c={c} cycles={list} onChanged={refresh} />}</DataBoundary>
          )}
          {tab === 'members' && <Members c={c} onChanged={refresh} />}
          {tab === 'timeline' && <Timeline c={c} />}
          {tab === 'rules' && <Rules c={c} />}
        </Screen>
      )}
    </DataBoundary>
  );
}

const roundHref = (c: CircleView, cy: { id: string }) => circleCycleHref(c.id, cy.id);

function Overview({ c, cycles, onChanged }: { c: CircleView; cycles: CycleSummary[] | undefined; onChanged: () => void }) {
  const session = useSession();
  const dashboard = useApi(`dash:${sessionKey(session)}:${c.id}:${cycles?.[0]?.state ?? ''}:${cycles?.[0]?.obligations_settled ?? ''}`,
    (s) => api.dashboard(session, c.id, s));
  const current = cycles?.[0];
  const org = c.my_role === 'organizer';
  const me = c.members.find((m) => m.id === c.my_member_id);
  const allWon = c.members.every((m) => m.has_won);
  const canStart = org && !allWon && (!current || current.state === 'FINALIZED');

  return (
    <div className="grid grid--main">
      <div className="stack stack--lg">
        {cycles === undefined ? <Skeleton /> : current ? (
          <Link href={roundHref(c, current)} className="card card--link">
            <div className="row row--between">
              <div>
                <p className="muted small">Current round</p>
                <h2>Round {current.number} of {c.ruleset.member_count}</h2>
              </div>
              <StateBadge state={current.state} />
            </div>
            <div className="stats">
              <Stat label="Due"><DueLine iso={current.due_date} /></Stat>
              <Stat label="Confirmed">{current.obligations_settled} of {current.obligations_total || c.members.length}</Stat>
              <Stat label="Recipient">{current.winner_member_id ? c.members.find((m) => m.id === current.winner_member_id)?.name ?? '—' : 'Not yet'}</Stat>
            </div>
            {current.obligations_total > 0 && (
              <ProgressBar value={current.obligations_settled} max={current.obligations_total} tone="income" label="Contributions confirmed"
                           right={`${current.obligations_settled}/${current.obligations_total}`} />
            )}
            <span className="link">Open round workspace <Icon name="chevronRight" /></span>
          </Link>
        ) : (
          <Card>
            <EmptyState icon="calendar" title="No rounds yet">
              {org ? 'Start the first round to open contributions.' : 'The organizer hasn’t started the first round yet.'}
            </EmptyState>
          </Card>
        )}

        {canStart && <StartRound c={c} nextNumber={(current?.number ?? 0) + 1} onStarted={onChanged} />}
        {org && allWon && current?.state === 'FINALIZED' && (
          <Banner tone="success" title="Circle complete">Every member has received the pot once. The circle’s record stays available.</Banner>
        )}

        {org && (
          <DataBoundary state={dashboard} skeleton={<Skeleton />}>
            {(d) => (
              <Card title="Collections this round" subtitle={d.summary.current_cycle_number ? `Round ${d.summary.current_cycle_number}` : undefined}>
                <div className="stats stats--4">
                  <Stat label="Confirmed"><Amount minor={d.collections.amount_collected} currency={c.currency} tone="income" /></Stat>
                  <Stat label="Outstanding"><Amount minor={d.collections.amount_outstanding} currency={c.currency} tone={d.collections.amount_outstanding ? 'warning' : 'default'} /></Stat>
                  <Stat label="Late">{d.collections.late}</Stat>
                  <Stat label="Received pot">{d.summary.won_members} of {d.summary.total_members}</Stat>
                </div>
                {d.risk.late_members.length > 0 && (
                  <ul className="list">
                    {d.risk.late_members.map((m) => (
                      <li key={m.member_id} className="list__row">
                        <Avatar name={m.member_name ?? '?'} small />
                        <span className="grow">{m.member_name}</span>
                        <Pill tone={m.is_late ? 'danger' : 'warning'}>{m.is_late ? 'Late' : 'Pending'}</Pill>
                        <Amount minor={m.outstanding} currency={c.currency} />
                      </li>
                    ))}
                  </ul>
                )}
                {d.collections.late > 0 && (
                  <LinkButton href={agentsHref(c.id)} variant="soft" small icon="bot">Ask the collections agent to follow up</LinkButton>
                )}
              </Card>
            )}
          </DataBoundary>
        )}
      </div>

      <div className="stack stack--lg">
        {me ? (
          <Card title="Your seat">
            <KeyValue rows={[
              ['Seat', `#${me.position}`],
              ['Received the pot', me.has_won ? 'Yes' : 'Not yet'],
              ['Security', <Pill key="s" tone={SECURITY_INFO[me.security_status]?.tone ?? 'neutral'}>{SECURITY_INFO[me.security_status]?.label ?? me.security_status}</Pill>],
              ['Due this round', current && current.my_outstanding !== null
                ? (paymentOpen(c.ruleset.payout_mode, current)
                  ? <Amount key="d" minor={current.my_outstanding} currency={c.currency} tone={current.my_outstanding ? 'warning' : 'income'} />
                  : <span key="d" className="muted">{isAuction(c.ruleset.payout_mode) ? 'After the auction' : '—'}</span>)
                : '—'],
            ]} />
            {current && <LinkButton href={roundHref(c, current)} small variant="secondary">Go to round {current.number}</LinkButton>}
          </Card>
        ) : (
          <Card title="Your role"><p className="muted">You organize this circle but don’t hold a seat, so you don’t contribute or receive the pot.</p></Card>
        )}
        <Card title="At a glance">
          <KeyValue rows={[
            ['Rounds completed', `${cycles?.filter((x) => x.state === 'FINALIZED').length ?? 0} of ${c.ruleset.member_count}`],
            ['Rules version', `v${c.ruleset_version}`],
            ['Grace period', `${c.ruleset.grace_period_days} days`],
            ['Approvals needed', String(c.ruleset.required_approvals)],
          ]} />
        </Card>
      </div>
    </div>
  );
}

function StartRound({ c, nextNumber, onStarted }: { c: CircleView; nextNumber: number; onStarted: () => void }) {
  const session = useSession();
  const router = useRouter();
  const toast = useToast();
  const [date, setDate] = useState(() => new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10));
  const start = useAction(async () => {
    const cy = await api.createCycle(session, c.id, `${date}T12:00:00Z`);
    await api.openCycle(session, cy.id);
    toast(`Round ${nextNumber} opened for contributions`);
    onStarted();
    router.push(roundHref(c, cy));
  });
  return (
    <Card title={`Start round ${nextNumber}`} subtitle="Creates the round and opens contributions for every member." tone="soft">
      <form className="row row--wrap row--top" onSubmit={(e) => { e.preventDefault(); void start.run(); }}>
        <div className="grow" style={{ minWidth: 200 }}>
          <Field label="Contributions due on" help="Pick a past date to simulate overdue members in the sandbox.">
            {(id) => <input id={id} type="date" value={date} onChange={(e) => setDate(e.target.value)} required />}
          </Field>
        </div>
        <Button type="submit" icon="play" disabled={start.pending || !date} style={{ marginTop: 26 }}>{start.pending ? 'Starting…' : 'Start round'}</Button>
      </form>
      {start.error && <Banner tone="danger">{start.error}</Banner>}
    </Card>
  );
}

function Rounds({ c, cycles, onChanged }: { c: CircleView; cycles: CycleSummary[]; onChanged: () => void }) {
  const current = cycles[0];
  const canStart = c.my_role === 'organizer' && !c.members.every((m) => m.has_won) && (!current || current.state === 'FINALIZED');
  return (
    <div className="stack stack--lg">
      {canStart && <StartRound c={c} nextNumber={(current?.number ?? 0) + 1} onStarted={onChanged} />}
      <Card title="All rounds">
        {cycles.length === 0 ? <p className="muted">No rounds yet.</p> : (
          <ul className="list">
            {cycles.map((cy) => (
              <li key={cy.id}>
                <Link href={roundHref(c, cy)} className="list__row">
                  <span className="glyph glyph--brand"><b>{cy.number}</b></span>
                  <span className="grow">
                    <span className="list__title">Round {cy.number} <StateBadge state={cy.state} /></span>
                    <span className="muted small">Due {formatDate(cy.due_date)} · {cy.obligations_settled}/{cy.obligations_total} confirmed
                      {cy.winner_member_id ? ` · Recipient: ${c.members.find((m) => m.id === cy.winner_member_id)?.name ?? '—'}` : ''}</span>
                  </span>
                  {cy.discount !== null && <Amount minor={cy.discount} currency={c.currency} tone="muted" />}
                  <Icon name="chevronRight" width={18} height={18} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Members({ c, onChanged }: { c: CircleView; onChanged: () => void }) {
  const session = useSession();
  const toast = useToast();
  const org = c.my_role === 'organizer';
  const [risk, setRisk] = useState<{ member: MemberView; data?: RiskView; error?: string } | null>(null);
  const setSecurity = useAction(async (m: MemberView, status: string) => {
    await api.setSecurity(session, c.id, m.id, status);
    toast(`${m.name}: ${SECURITY_INFO[status]?.label ?? status}`);
    onChanged();
  });
  const openRisk = async (member: MemberView) => {
    setRisk({ member });
    try { setRisk({ member, data: await api.memberRisk(session, c.id, member.id) }); }
    catch (e) { setRisk({ member, error: (e as Error).message }); }
  };

  return (
    <Card title={`${c.members.length} members`} subtitle={org ? 'Security status gates payouts when the rules require it.' : undefined}>
      {setSecurity.error && <Banner tone="danger">{setSecurity.error}</Banner>}
      <ul className="list">
        {c.members.map((m) => {
          const you = m.id === c.my_member_id;
          const sec = SECURITY_INFO[m.security_status] ?? { label: m.security_status, tone: 'neutral' as const };
          return (
            <li key={m.id} className="list__row">
              <Avatar name={m.name} you={you} />
              <div className="grow">
                <div className="list__title">
                  {m.name}{you && <span className="muted">(you)</span>}
                  {m.has_won && <Pill tone="brand" icon="trophy">Received pot</Pill>}
                </div>
                <div className="muted small">
                  Seat #{m.position} · {m.linked ? 'Account linked' : m.invite_email ? `Invited: ${m.invite_email}` : 'Managed by organizer'}
                </div>
              </div>
              {org ? (
                <div className="member-row">
                  <select aria-label={`Security status for ${m.name}`} value={m.security_status} disabled={setSecurity.pending}
                          onChange={(e) => void setSecurity.run(m, e.target.value)}>
                    {Object.entries(SECURITY_INFO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                  <Button variant="ghost" small onClick={() => void openRisk(m)}>Risk</Button>
                </div>
              ) : <Pill tone={sec.tone}>{sec.label}</Pill>}
            </li>
          );
        })}
      </ul>
      <Modal open={!!risk} title={risk ? `Risk indicators · ${risk.member.name}` : ''} onClose={() => setRisk(null)}>
        {risk && !risk.data && !risk.error && <Skeleton kind="line" count={3} />}
        {risk?.error && <Banner tone="danger">{risk.error}</Banner>}
        {risk?.data && (
          <>
            <div className="row"><Pill tone={risk.data.indicator === 'LOW' ? 'success' : risk.data.indicator === 'MEDIUM' ? 'warning' : 'danger'}>{humanize(risk.data.indicator)} risk</Pill>
              <span className="muted">{risk.data.points} points</span></div>
            {risk.data.factors.length ? <ul className="rules-list">{risk.data.factors.map((f) => <li key={f}>{humanize(f)}</li>)}</ul>
              : <p className="muted">No risk factors recorded.</p>}
            <KeyValue rows={[['Suggested security', humanize(risk.data.required_security_level)], ['Recommendation', risk.data.review_recommendation]]} />
            <Banner tone="neutral">{risk.data.disclaimer}</Banner>
          </>
        )}
      </Modal>
    </Card>
  );
}

const CELL_ICON: Record<string, ReactNode> = {
  PAID: <Icon name="check" />, LATE: '!', PENDING: '·', WINNER: <Icon name="trophy" />, AUCTION: <Icon name="gavel" />, NOT_OPEN: '',
};

function Timeline({ c }: { c: CircleView }) {
  const session = useSession();
  const tl = useApi<TimelineView>(`timeline:${sessionKey(session)}:${c.id}`, (s) => api.timeline(session, c.id, s));
  return (
    <Card title="Member × round timeline" subtitle="Who has paid, who is late, and who received each pot.">
      <DataBoundary state={tl}>
        {(t) => t.cycles.length === 0 ? <p className="muted">The timeline fills in as rounds run.</p> : (
          <>
            <div className="timeline">
              <table>
                <thead>
                  <tr><th className="member">Member</th>{t.cycles.map((cy) => <th key={cy.cycle_id}>R{cy.cycle_number}</th>)}</tr>
                </thead>
                <tbody>
                  {t.members.map((m) => (
                    <tr key={m.member_id}>
                      <th className="member">{m.member_name}{m.member_id === c.my_member_id ? ' (you)' : ''}</th>
                      {m.cycles.map((cell) => (
                        <td key={cell.cycle_id}>
                          <span className={`cell cell--${cell.state}`} title={`${humanize(cell.state)} · Round ${cell.cycle_number}`}>
                            {CELL_ICON[cell.state]}
                          </span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="legend">
              {(['PAID', 'PENDING', 'LATE', 'AUCTION', 'WINNER', 'NOT_OPEN'] as const).map((s) => (
                <span key={s}><i className={`cell--${s}`} />{s === 'NOT_OPEN' ? 'Not opened' : humanize(s)}</span>
              ))}
            </div>
          </>
        )}
      </DataBoundary>
    </Card>
  );
}

function Rules({ c }: { c: CircleView }) {
  return (
    <div className="grid grid--main">
      <Card title="How this circle works" subtitle={`Rules version ${c.ruleset_version} · applied by the settlement engine`}>
        <ul className="rules-list">{describeRules(c.ruleset).map((s) => <li key={s}>{s}</li>)}</ul>
      </Card>
      <Card title="Rule versions" subtitle="A round always keeps the version it started with.">
        <ul className="list">
          {[...c.rulesets].reverse().map((r) => (
            <li key={r.version} className="list__row">
              <div className="grow">
                <div className="list__title">Version {r.version} <Pill tone={r.status === 'ACTIVE' ? 'success' : 'neutral'}>{humanize(r.status)}</Pill></div>
                <div className="muted small">{r.reason}{r.created_at ? ` · ${formatDate(r.created_at)}` : ''}</div>
                <div className="mono muted" title={r.fingerprint}>{r.fingerprint.slice(0, 24)}…</div>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
