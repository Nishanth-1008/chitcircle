'use client';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import type { ApiState } from '@/lib/hooks';
import { DEFAULT_CURRENCY } from '@/lib/config';
import { myObligation, settledCount } from '@/lib/derive';
import { dueLabel, formatDate, formatDateTime } from '@/lib/format';
import { describeLedgerEvent } from '@/lib/ledger';
import type { OverviewItem } from '@/lib/overview';
import type { Actor } from '@/lib/permissions';
import { roleIn } from '@/lib/permissions';
import { ROUND_STEPS, phaseOf, stateInfo } from '@/lib/status';
import type { CycleView, LedgerEventView, MemberView, SettlementData } from '@/lib/types';
import { Icon } from './Icon';
import { Amount, DemoPill, ErrorState, ProgressBar, Skeleton, StaleNotice, StatusPill } from './ui';

/** Loading / error / stale handling in one place. Empty states are rendered by the caller. */
export function DataBoundary<T>({ state, skeleton, children }: {
  state: ApiState<T>; skeleton?: ReactNode; children: (data: T) => ReactNode;
}) {
  if (state.data === undefined) {
    if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;
    return <>{skeleton ?? <Skeleton count={3} />}</>;
  }
  return (
    <>
      {state.stale && <StaleNotice updatedAt={state.updatedAt} onRetry={state.refetch} />}
      {children(state.data)}
    </>
  );
}

export function StateBadge({ state }: { state: string }) {
  const s = stateInfo(state);
  return <StatusPill tone={s.tone}>{s.label}</StatusPill>;
}

export function RoundStepper({ state, priorState }: { state: string; priorState: string | null }) {
  const current = phaseOf(state, priorState);
  return (
    <ol className="steps" aria-label="Round progress">
      {ROUND_STEPS.map((label, i) => (
        <li key={label} className="step" data-state={i < current ? 'done' : i === current ? 'current' : 'todo'}
            aria-current={i === current ? 'step' : undefined}>
          <i />{label}
        </li>
      ))}
    </ol>
  );
}

export function CircleCard({ item, actor, currency, assumed }: {
  item: OverviewItem; actor: Actor | null; currency: string; assumed: boolean;
}) {
  const { circle, round } = item;
  if (!circle) return null;
  const role = roleIn(circle, actor);
  const mine = myObligation(round, actor);
  const total = round?.obligations?.length ?? 0;
  const href = `/app/circles/${encodeURIComponent(circle.id)}`;
  return (
    <Link href={href} className="card stack" aria-label={`Open ${circle.name}`}>
      <div className="circle-card__top">
        <div className="grow">
          <p className="circle-card__name">{circle.name}</p>
          <p className="muted">
            {circle.members.length} members{round ? ` · Round ${round.number}` : ''}
          </p>
        </div>
        {round ? <StateBadge state={round.state} /> : <StatusPill>No round saved</StatusPill>}
      </div>
      {round && (
        <div className="stats">
          <div><div className="stat__label">Next due</div><div className="stat__value">{formatDate(round.due_date, true)}</div></div>
          <div><div className="stat__label">Your balance</div>
            <div className="stat__value">{mine
              ? <Amount minor={mine.outstanding} currency={currency} assumed={assumed} tone={mine.outstanding > 0 ? 'warning' : 'income'} />
              : '—'}</div></div>
          <div><div className="stat__label">Your role</div>
            <div className="stat__value">{role === 'organizer' ? 'Organizer' : role === 'member' ? 'Member' : 'Viewer'}</div></div>
        </div>
      )}
      {round && total > 0 && (
        <ProgressBar value={settledCount(round)} max={total} label="Contributions settled" right={`${settledCount(round)} of ${total}`} />
      )}
    </Link>
  );
}

export function DueCard({ circleName, circleId, round, mineOutstanding, currency, assumed }: {
  circleName: string; circleId: string; round: CycleView; mineOutstanding: number; currency: string; assumed: boolean;
}) {
  return (
    <section className="card due-card" aria-label="Next installment due">
      <StatusPill tone="warning" icon="clock">Due {formatDate(round.due_date, true)} · {dueLabel(round.due_date)}</StatusPill>
      <div className="due-card__amount">
        <Amount minor={mineOutstanding} currency={currency} assumed={assumed} size="lg" />
        <span className="muted">{circleName} · Round {round.number}</span>
      </div>
      <p className="muted">Online payment isn’t connected yet. A contribution counts only after the payment provider confirms it.</p>
      <Link className="link" href={`/app/circles/${encodeURIComponent(circleId)}/cycles/${encodeURIComponent(round.id)}`}>
        View this round <Icon name="chevronRight" />
      </Link>
    </section>
  );
}

export function ActivityRow({ event, memberById, demo, expanded, onToggle, assumedCurrency }: {
  event: LedgerEventView; memberById: (id: string | null) => MemberView | undefined; demo: boolean;
  expanded: boolean; onToggle: () => void; assumedCurrency?: boolean;
}) {
  const d = describeLedgerEvent(event);
  const member = memberById(event.member_id);
  const tone = d.direction === 'in' ? 'income' : d.direction === 'out' ? 'expense' : d.statusTone === 'danger' ? 'expense' : d.pending ? 'warning' : 'muted';
  const sign = d.direction === 'in' ? 1 : d.direction === 'out' ? -1 : 0;
  const detailId = `ev-${event.id}`;
  return (
    <li className="activity__item">
      <button type="button" className="activity__btn" aria-expanded={expanded} aria-controls={detailId} onClick={onToggle}>
        <span className={`glyph glyph--${d.glyph}`}><Icon name={d.icon} /></span>
        <span className="grow">
          <span className="activity__title">{d.title}</span>
          <span className="activity__meta" style={{ display: 'block' }}>
            {member ? member.name : event.member_id ? 'Member' : 'Circle'} · {formatDateTime(event.timestamp)}
          </span>
        </span>
        <span className="activity__right">
          <Amount minor={sign * event.amount} currency={event.currency} tone={tone} precise signed={sign > 0} />
          <span className="row" style={{ gap: 4 }}>
            {demo && <DemoPill />}
            <StatusPill tone={d.statusTone}>{d.status}</StatusPill>
          </span>
        </span>
      </button>
      {expanded && (
        <div className="detail" id={detailId}>
          <dl>
            <dt>Event ID</dt><dd className="num">{event.id}</dd>
            <dt>Recorded by</dt><dd>{event.actor}</dd>
            <dt>Rule version</dt><dd>{event.ruleset_version}</dd>
            {event.provider_ref && (<><dt>Provider ref</dt><dd className="num">{event.provider_ref}</dd></>)}
            {event.settlement_id && (<><dt>Settlement</dt>
              <dd><Link className="link" href={`/app/settlements/${encodeURIComponent(event.settlement_id)}`}>Open settlement</Link></dd></>)}
            {event.reason && (<><dt>Reason</dt><dd>{event.reason}</dd></>)}
            {event.reverses && (<><dt>Reverses</dt><dd className="num">{event.reverses}</dd></>)}
          </dl>
          {event.journal && (
            <table className="postings">
              <caption className="sr-only">Journal postings</caption>
              <thead><tr><th>Account</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
              <tbody>
                {event.journal.postings.map((p, i) => (
                  <tr key={i}>
                    <td>{p.account}</td>
                    <td className="num">{p.debit ? <Amount minor={p.debit} currency={event.journal!.currency} precise /> : '—'}</td>
                    <td className="num">{p.credit ? <Amount minor={p.credit} currency={event.journal!.currency} precise /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {assumedCurrency && <p className="muted">Currency shown as {DEFAULT_CURRENCY} (assumed).</p>}
        </div>
      )}
    </li>
  );
}

export function useExpandable() {
  const [open, setOpen] = useState<string | null>(null);
  return { open, toggle: (id: string) => setOpen((o) => (o === id ? null : id)) };
}

/** Renders the settlement exactly as the server returned it. No totals are recomputed here. */
export function FinancialBreakdown({ data, actorId, nameOf }: {
  data: SettlementData; actorId: string | undefined; nameOf: (id: string) => string;
}) {
  const c = data.currency;
  const myNet = actorId ? data.net_contributions[actorId] : undefined;
  const row = (label: string, hint: string, minor: number, tone?: 'income' | 'expense', total?: boolean) => (
    <div className={`breakdown__row${total ? ' breakdown__row--total' : ''}`}>
      <div><span style={{ fontWeight: total ? 700 : 500 }}>{label}</span><small>{hint}</small></div>
      <Amount minor={minor} currency={c} tone={tone} precise />
    </div>
  );
  return (
    <div className="stack stack--lg">
      <section className="card" aria-label="Settlement breakdown">
        <div className="breakdown">
          {row('Gross chit value', 'Total pot for this round', data.chit_value.minor)}
          {row('Winning discount', 'Accepted by the auction or agreement', data.discount.minor, 'expense')}
          {row('Winner payout', 'Amount the recipient receives', data.winner_payout.minor, 'income', true)}
          {row('Organizer commission', 'Per the circle’s rules', data.commission.minor)}
          {row('Dividend pool', 'Shared among eligible members', data.dividend_pool.minor)}
          {row('Rounding adjustment', data.remainder_destination ? `Goes to ${data.remainder_destination.toLowerCase().replace('_', ' ')}` : 'None recorded', data.rounding_remainder.minor)}
        </div>
      </section>
      {myNet && (
        <section className="card card--soft" aria-label="Your net contribution">
          <p className="muted">Your net contribution</p>
          <Amount minor={myNet.minor} currency={c} size="lg" precise />
          <p className="muted">After your dividend of {data.dividends[actorId!] ? <Amount minor={data.dividends[actorId!].minor} currency={c} precise /> : '—'}</p>
        </section>
      )}
      <section className="card" aria-label="Per member">
        <h3 style={{ marginBottom: 4 }}>Per member</h3>
        <ul>
          {data.member_order.map((id) => (
            <li key={id} className="listrow">
              <div className="grow">
                <div style={{ fontWeight: 600 }}>{nameOf(id)}{id === data.winner_member_id && <> <StatusPill tone="brand" icon="trophy">Winner</StatusPill></>}</div>
                <div className="muted">Dividend <Amount minor={data.dividends[id]?.minor} currency={c} precise /></div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="muted" style={{ fontSize: 12 }}>Net contribution</div>
                <Amount minor={data.net_contributions[id]?.minor} currency={c} precise />
              </div>
            </li>
          ))}
        </ul>
      </section>
      {data.adjustments.length > 0 && (
        <section className="card" aria-label="Adjustments">
          <h3 style={{ marginBottom: 4 }}>Adjustments</h3>
          <ul>{data.adjustments.map((a, i) => (
            <li key={i} className="listrow"><div className="grow">{a.reason}<div className="muted">{a.calculation}</div></div>
              <Amount minor={a.amount.minor} currency={a.amount.currency} precise /></li>))}</ul>
        </section>
      )}
    </div>
  );
}
