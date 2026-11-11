'use client';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import { dueLabel, formatDate, formatDateTime } from '@/lib/format';
import type { ApiState } from '@/lib/hooks';
import { circleHref, settlementHref } from '@/lib/routes';
import { describeLedgerEvent } from '@/lib/ledger';
import { currencySymbol, parseMajorToMinor } from '@/lib/money';
import { payoutModeTitle } from '@/lib/ruleset';
import { ROUND_STEPS, phaseOf, stateInfo } from '@/lib/status';
import type { LedgerEventView, MyCircle, SettlementData } from '@/lib/types';
import { paymentOpen } from '@/lib/workflow';
import { Icon } from './Icon';
import { Amount, ErrorState, Pill, ProgressBar, Skeleton, StaleNotice } from './ui';

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
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

export function RoleBadge({ role }: { role: string }) {
  if (role === 'organizer') return <Pill tone="brand" icon="shield">Organizer</Pill>;
  if (role === 'member') return <Pill tone="neutral" icon="users">Member</Pill>;
  return <Pill tone="neutral">Viewer</Pill>;
}

export function RoundStepper({ state, priorState }: { state: string; priorState: string | null }) {
  const current = phaseOf(state, priorState);
  const done = state === 'FINALIZED';
  return (
    <ol className="steps" aria-label="Round progress">
      {ROUND_STEPS.map((label, i) => (
        <li key={label} className="step" data-state={done || i < current ? 'done' : i === current ? 'current' : 'todo'}
            aria-current={!done && i === current ? 'step' : undefined}>
          <i>{done || i < current ? <Icon name="check" /> : i + 1}</i><span>{label}</span>
        </li>
      ))}
    </ol>
  );
}

export function CircleCard({ c }: { c: MyCircle }) {
  const cy = c.current_cycle;
  const href = circleHref(c.id);
  const owes = cy && cy.my_outstanding !== null && cy.my_outstanding > 0 && paymentOpen(c.payout_mode, cy);
  return (
    <Link href={href} className="card card--link circle-card" aria-label={`Open ${c.name}`}>
      <div className="circle-card__top">
        <div className="grow">
          <p className="circle-card__name">{c.name}</p>
          <p className="muted small">{payoutModeTitle(c.payout_mode)} · {c.member_count} members</p>
        </div>
        {cy ? <StateBadge state={cy.state} /> : <Pill>No rounds yet</Pill>}
      </div>
      <div className="stats">
        <div className="stat"><div className="stat__label">Pot</div><div className="stat__value"><Amount minor={c.total_chit_value} currency={c.currency} /></div></div>
        <div className="stat"><div className="stat__label">Round</div><div className="stat__value">{cy ? `${cy.number} of ${c.member_count}` : '—'}</div></div>
        <div className="stat"><div className="stat__label">{c.my_member_id ? 'You owe' : 'Your role'}</div>
          <div className="stat__value">{c.my_member_id
            ? (owes ? <Amount minor={cy!.my_outstanding} currency={c.currency} tone="warning" /> : <span className="income">Nothing due</span>)
            : 'Organizer'}</div></div>
      </div>
      {cy && cy.obligations_total > 0 && (
        <ProgressBar value={cy.obligations_settled} max={cy.obligations_total} tone="income"
                     label="Contributions confirmed" right={`${cy.obligations_settled} of ${cy.obligations_total}`} />
      )}
      <div className="circle-card__foot muted small">
        {c.my_role === 'organizer' ? <span><Icon name="shield" /> You organize this circle</span> : <span><Icon name="users" /> Member</span>}
        {cy && <span><Icon name="calendar" /> Due {formatDate(cy.due_date, true)}</span>}
        {c.pending_actions > 0 && <span className="brand"><Icon name="bot" /> {c.pending_actions} to review</span>}
      </div>
    </Link>
  );
}

export function DueLine({ iso }: { iso: string }) {
  const label = dueLabel(iso);
  return <span className={label.includes('overdue') ? 'expense' : 'muted'}>Due {formatDate(iso, true)} · {label}</span>;
}

export function ActivityRow({ event, nameOf, expanded, onToggle, showRound }: {
  event: LedgerEventView; nameOf: (id: string | null) => string; expanded: boolean; onToggle: () => void; showRound?: boolean;
}) {
  const d = describeLedgerEvent(event);
  const tone = d.direction === 'in' ? 'income' : d.direction === 'out' ? 'expense' : d.statusTone === 'danger' ? 'expense' : d.pending ? 'warning' : 'muted';
  const sign = d.direction === 'out' ? -1 : 1;
  const detailId = `ev-${event.id}`;
  return (
    <li className="activity__item">
      <button type="button" className="activity__btn" aria-expanded={expanded} aria-controls={detailId} onClick={onToggle}>
        <span className={`glyph glyph--${d.glyph}`}><Icon name={d.icon} /></span>
        <span className="grow">
          <span className="activity__title">{d.title}</span>
          <span className="activity__meta">
            {event.member_id ? nameOf(event.member_id) : 'Circle'}
            {showRound && event.cycle_number ? ` · Round ${event.cycle_number}` : ''} · {formatDateTime(event.timestamp)}
          </span>
        </span>
        <span className="activity__right">
          <Amount minor={sign * event.amount} currency={event.currency} tone={tone} precise signed={d.direction === 'in'} />
          <Pill tone={d.statusTone}>{d.status}</Pill>
        </span>
      </button>
      {expanded && (
        <div className="detail" id={detailId}>
          <dl className="kv kv--compact">
            <div><dt>Event ID</dt><dd className="num mono">{event.id}</dd></div>
            <div><dt>Recorded by</dt><dd>{event.actor}</dd></div>
            <div><dt>Rule version</dt><dd>v{event.ruleset_version}</dd></div>
            {event.provider_ref && <div><dt>Provider ref</dt><dd className="mono">{event.provider_ref}</dd></div>}
            {event.settlement_id && <div><dt>Settlement</dt>
              <dd><Link className="link" href={settlementHref(event.settlement_id)}>Open settlement</Link></dd></div>}
            {event.reason && <div><dt>Reason</dt><dd>{event.reason}</dd></div>}
            {event.reverses && <div><dt>Reverses</dt><dd className="mono">{event.reverses}</dd></div>}
          </dl>
          {event.journal && (
            <table className="postings">
              <caption className="sr-only">Journal postings</caption>
              <thead><tr><th>Account</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
              <tbody>
                {event.journal.postings.map((p, i) => (
                  <tr key={i}>
                    <td className="mono">{p.account}</td>
                    <td className="num">{p.debit ? <Amount minor={p.debit} currency={event.journal!.currency} precise /> : '—'}</td>
                    <td className="num">{p.credit ? <Amount minor={p.credit} currency={event.journal!.currency} precise /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </li>
  );
}

export function useExpandable() {
  const [open, setOpen] = useState<string | null>(null);
  return { open, toggle: (id: string) => setOpen((o) => (o === id ? null : id)) };
}

export function ActivityList({ events, nameOf, showRound, empty = 'Nothing recorded yet.' }: {
  events: LedgerEventView[]; nameOf: (id: string | null) => string; showRound?: boolean; empty?: string;
}) {
  const { open, toggle } = useExpandable();
  if (events.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="activity">
      {events.map((e) => (
        <ActivityRow key={e.id} event={e} nameOf={nameOf} expanded={open === e.id} onToggle={() => toggle(e.id)} showRound={showRound} />
      ))}
    </ul>
  );
}

/** Renders the settlement exactly as the server returned it. No totals are recomputed here. */
export function FinancialBreakdown({ data, myMemberId, nameOf }: {
  data: SettlementData; myMemberId: string | null; nameOf: (id: string) => string;
}) {
  const c = data.currency;
  const myNet = myMemberId ? data.net_contributions[myMemberId] : undefined;
  const discountFunded = data.discount.minor > 0;
  const row = (label: string, hint: string, minor: number, tone?: 'income' | 'expense', total?: boolean) => (
    <div className={`breakdown__row${total ? ' breakdown__row--total' : ''}`}>
      <div><span className="breakdown__label">{label}</span><small>{hint}</small></div>
      <Amount minor={minor} currency={c} tone={tone} precise />
    </div>
  );
  return (
    <div className="grid grid--2">
      <section className="card" aria-label="Settlement breakdown">
        <h3 className="card__title">Where the pot goes</h3>
        <div className="breakdown">
          {row('Pot (chit value)', 'Collected from every member this round', data.chit_value.minor)}
          {discountFunded && row('Winning discount', 'Given up by the recipient in the auction', data.discount.minor, 'expense')}
          {row('Recipient receives', `${nameOf(data.winner_member_id)} · pot minus discount`, data.winner_payout.minor, 'income', true)}
          {row('Organizer commission', 'Per the circle’s rules', data.commission.minor)}
          {discountFunded && row('Dividend pool', 'Discount minus commission, shared back', data.dividend_pool.minor)}
          {data.rounding_remainder.minor > 0 && row('Rounding remainder',
            `Goes to ${(data.remainder_destination ?? 'the configured destination').toLowerCase().replace('_', ' ')}`, data.rounding_remainder.minor)}
        </div>
      </section>
      <div className="stack">
        {myNet && (
          <section className="card card--soft" aria-label="Your net installment">
            <p className="muted small">Your net installment this round</p>
            <Amount minor={myNet.minor} currency={c} size="xl" precise />
            <p className="muted small">
              Your share <Amount minor={data.contributions[myMemberId!]?.minor} currency={c} precise /> minus your dividend <Amount minor={data.dividends[myMemberId!]?.minor} currency={c} precise />
            </p>
          </section>
        )}
        <section className="card" aria-label="Per member">
          <h3 className="card__title">Per member</h3>
          <ul className="list">
            {data.member_order.map((id) => (
              <li key={id} className="list__row">
                <div className="grow">
                  <div className="list__title">{nameOf(id)}{id === myMemberId && <span className="muted"> (you)</span>}
                    {id === data.winner_member_id && <> <Pill tone="brand" icon="trophy">Recipient</Pill></>}</div>
                  {discountFunded && <div className="muted small">Dividend <Amount minor={data.dividends[id]?.minor} currency={c} precise /></div>}
                </div>
                <div className="right">
                  <div className="muted small">Net installment</div>
                  <Amount minor={data.net_contributions[id]?.minor} currency={c} precise />
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

/** Amount input in major units; the parsed value is exact integer minor units (or null when invalid). */
export function MoneyInput({ id, currency, value, onChange, placeholder, invalid }: {
  id: string; currency: string; value: string; onChange: (raw: string, minor: number | null) => void;
  placeholder?: string; invalid?: boolean;
}) {
  return (
    <div className="money-input">
      <span className="money-input__sym">{currencySymbol(currency)}</span>
      <input id={id} inputMode="decimal" autoComplete="off" value={value} placeholder={placeholder}
             aria-invalid={invalid || undefined}
             onChange={(e) => onChange(e.target.value, parseMajorToMinor(e.target.value, currency))} />
    </div>
  );
}
