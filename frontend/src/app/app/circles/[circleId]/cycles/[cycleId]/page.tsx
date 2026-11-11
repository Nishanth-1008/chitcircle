'use client';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/Icon';
import { ActivityList, DataBoundary, DueLine, MoneyInput, RoundStepper, StateBadge } from '@/components/domain';
import { Screen } from '@/components/shell';
import {
  Amount, Avatar, Banner, Button, Card, Field, KeyValue, LinkButton, Modal, Pill, ProgressBar, Skeleton, Stat,
} from '@/components/ui';
import { useAppConfig } from '@/lib/appConfig';
import { api } from '@/lib/api/endpoints';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAction, useApi, type ApiState } from '@/lib/hooks';
import { isAuction } from '@/lib/ruleset';
import { sessionKey, useSession } from '@/lib/session';
import { humanize, reasonLabel, stateInfo } from '@/lib/status';
import { useToast } from '@/lib/toast';
import type { AppConfigView, BidView, CircleView, CycleView, ObligationView } from '@/lib/types';
import { ACTIVE_POLL_STATES, paymentOpen } from '@/lib/workflow';

export default function RoundPage() {
  return <Suspense fallback={<div className="page"><Skeleton count={3} /></div>}><Round /></Suspense>;
}

function Round() {
  const { circleId, cycleId } = useParams<{ circleId: string; cycleId: string }>();
  const params = useSearchParams();
  const session = useSession();
  const key = sessionKey(session);
  const circle = useApi(`circle:${key}:${circleId}`, (s) => api.getCircle(session, circleId, s));
  const [poll, setPoll] = useState(false);
  const cycle = useApi(`cycle:${key}:${cycleId}`, (s) => api.getCycle(session, cycleId, s), { pollMs: poll ? 4000 : 20000 });
  useEffect(() => { setPoll(!!cycle.data && ACTIVE_POLL_STATES.includes(cycle.data.state)); }, [cycle.data]);
  const version = cycle.data ? `${cycle.data.state}:${cycle.data.transitions.length}:${cycle.data.obligations.map((o) => o.confirmed_paid).join(',')}` : '';
  const ledger = useApi(cycle.data ? `cledger:${key}:${cycleId}:${version}` : null, (s) => api.cycleLedger(session, cycleId, s));
  const showBids = !!cycle.data && isAuction(cycle.data.payout_mode) && !['DRAFT', 'OPEN', 'COLLECTIONS_IN_PROGRESS'].includes(cycle.data.state);
  const bids = useApi<BidView[]>(showBids ? `bids:${key}:${cycleId}:${cycle.data?.state}` : null, (s) => api.listBids(session, cycleId, s),
    { pollMs: cycle.data?.state === 'AUCTION_OPEN' ? 4000 : undefined });
  const config = useAppConfig();
  const refresh = () => { cycle.refetch(); circle.refetch(); bids.refetch(); };

  return (
    <DataBoundary state={circle} skeleton={<div className="page"><Skeleton count={3} /></div>}>
      {(c) => (
        <DataBoundary state={cycle} skeleton={<div className="page"><Skeleton count={3} /></div>}>
          {(cy) => {
            const nameOf = (id: string | null) => (id && c.members.find((m) => m.id === id)?.name) || (id ? 'Member' : 'Circle');
            return (
              <Screen
                wide
                title={`Round ${cy.number}`}
                back={{ href: `/app/circles/${encodeURIComponent(c.id)}`, label: c.name }}
                subtitle={<><StateBadge state={cy.state} /><DueLine iso={cy.due_date} />
                  {poll && <span className="muted small"><Icon name="refresh" width={12} height={12} /> Live</span>}</>}
              >
                {params.get('payment') === 'returned' && (
                  <Banner tone="info" title="Back from PayPal">Your payment counts once PayPal confirms it to us; this page updates automatically.</Banner>
                )}
                {params.get('payment') === 'cancelled' && <Banner tone="warning">The PayPal payment was cancelled. Nothing was charged.</Banner>}
                <Card><RoundStepper state={cy.state} priorState={cy.prior_state} /></Card>
                <div className="grid grid--main">
                  <div className="stack stack--lg">
                    <NextStep c={c} cy={cy} bids={bids.data} nameOf={nameOf} onChanged={refresh} />
                    {showBids && <Bids c={c} cy={cy} bids={bids} nameOf={nameOf} />}
                    <Contributions c={c} cy={cy} config={config} nameOf={nameOf} onChanged={refresh} />
                    <Card title="Round activity" subtitle="Ledger entries for this round. Tap one to see its journal postings.">
                      <DataBoundary state={ledger} skeleton={<Skeleton kind="line" count={4} />}>
                        {(page) => <ActivityList events={[...page.items].reverse()} nameOf={nameOf} />}
                      </DataBoundary>
                    </Card>
                  </div>
                  <div className="stack stack--lg">
                    {c.my_member_id && cy.obligations.some((o) => o.member_id === c.my_member_id) && (
                      <Explanation c={c} cy={cy} />
                    )}
                    <Card title="Round facts">
                      <KeyValue rows={[
                        ['Due date', formatDate(cy.due_date)],
                        ['Rules version', `v${cy.ruleset_version}`],
                        ['Payout method', humanize(cy.payout_method ?? cy.payout_mode)],
                        ['Recipient', cy.winner_member_id ? nameOf(cy.winner_member_id) : 'Not selected'],
                        ...(cy.discount !== null ? [['Winning discount', <Amount key="d" minor={cy.discount} currency={cy.currency} />] as [string, ReactNode]] : []),
                        ...(cy.settlement_id ? [['Settlement', <Link key="s" className="link" href={`/app/settlements/${encodeURIComponent(cy.settlement_id)}`}>Open <Icon name="chevronRight" /></Link>] as [string, ReactNode]] : []),
                      ]} />
                    </Card>
                    <History cy={cy} />
                    <Dispute c={c} cy={cy} onChanged={refresh} />
                  </div>
                </div>
              </Screen>
            );
          }}
        </DataBoundary>
      )}
    </DataBoundary>
  );
}

// ------------------------------------------------------------------ next step
function NextStep({ c, cy, bids, nameOf, onChanged }: {
  c: CircleView; cy: CycleView; bids: BidView[] | undefined; nameOf: (id: string | null) => string; onChanged: () => void;
}) {
  const session = useSession();
  const toast = useToast();
  const org = c.my_role === 'organizer';
  const auction = isAuction(cy.payout_mode);
  const settlementHref = cy.settlement_id ? `/app/settlements/${encodeURIComponent(cy.settlement_id)}` : null;
  const act = useAction(async (fn: () => Promise<unknown>, done: string) => {
    try { await fn(); toast(done); } finally { onChanged(); }
  });
  const [reasonOpen, setReasonOpen] = useState(false);
  const info = stateInfo(cy.state);

  let title = info.label;
  let body: ReactNode = info.hint;
  let actions: ReactNode = null;

  switch (cy.state) {
    case 'DRAFT':
      title = 'Contributions not opened';
      body = org ? 'Opening collections creates each member’s obligation and records it in the ledger.' : 'The organizer will open contributions soon.';
      if (org) actions = <Button icon="play" disabled={act.pending} onClick={() => void act.run(() => api.openCycle(session, cy.id), 'Collections opened')}>Open collections</Button>;
      break;
    case 'COLLECTIONS_IN_PROGRESS':
      if (!cy.winner_member_id) {
        if (auction) {
          title = 'Ready for the auction';
          body = 'Members bid a discount for this round’s pot. Installments are finalized after the auction, so contributions are collected once the settlement is calculated.';
          if (org) actions = <Button icon="gavel" disabled={act.pending} onClick={() => void act.run(() => api.openAuction(session, cy.id), 'Auction opened')}>Open the auction</Button>;
        } else {
          title = cy.payout_mode === 'LOTTERY' ? 'Draw this round’s recipient' : 'Select this round’s recipient';
          body = cy.payout_mode === 'LOTTERY'
            ? 'A committed random draw picks from members who have not received the pot yet.'
            : 'The next member in seat order who hasn’t received the pot is selected.';
          if (org) actions = <Button icon="trophy" disabled={act.pending} onClick={() => void act.run(() => api.selectRecipient(session, cy.id), 'Recipient selected')}>
            {cy.payout_mode === 'LOTTERY' ? 'Run the draw' : 'Select recipient'}</Button>;
        }
      } else {
        title = `${nameOf(cy.winner_member_id)} receives this round’s pot`;
        body = 'Calculate the settlement to fix every member’s installment and the recipient’s payout.';
        if (org) actions = <Button icon="scale" disabled={act.pending} onClick={() => void act.run(() => api.calculateSettlement(session, cy.id), 'Settlement calculated')}>Calculate settlement</Button>;
      }
      break;
    case 'AUCTION_OPEN':
      title = 'Auction is open';
      body = org ? 'Close the auction when bidding ends. The engine picks the highest valid discount and applies the tie-break rule.'
        : 'Bid the discount you’re willing to give up to receive the pot now. Bids are checked by the engine.';
      if (org) actions = <Button icon="gavel" disabled={act.pending} onClick={() => void act.run(() => api.closeAuction(session, cy.id), 'Auction closed')}>Close auction</Button>;
      break;
    case 'AUCTION_CLOSED':
      title = cy.winner_member_id ? `${nameOf(cy.winner_member_id)} won the auction` : 'Auction closed';
      body = 'Calculate the settlement to apply the discount, commission and dividends.';
      if (org) actions = <Button icon="scale" disabled={act.pending || !cy.winner_member_id} onClick={() => void act.run(() => api.calculateSettlement(session, cy.id), 'Settlement calculated')}>Calculate settlement</Button>;
      break;
    case 'SETTLEMENT_CALCULATED':
    case 'AWAITING_APPROVAL':
    case 'APPROVED':
    case 'PAYOUT_PENDING':
    case 'PAYOUT_SUBMITTED':
    case 'PAYOUT_CONFIRMED':
    case 'RECONCILIATION_PENDING':
      body = <>{info.hint}{cy.obligations.some((o) => o.outstanding > 0) && ' Contributions still outstanding are listed below.'}</>;
      if (settlementHref) actions = <LinkButton href={settlementHref} icon="scale">{org ? 'Review settlement' : 'View settlement'}</LinkButton>;
      break;
    case 'FINALIZED':
      title = 'Round complete';
      body = `${nameOf(cy.winner_member_id)} received the pot and every check passed. This round is closed.`;
      if (settlementHref) actions = <LinkButton href={settlementHref} variant="secondary" icon="receipt">View settlement</LinkButton>;
      break;
    case 'ON_HOLD':
    case 'FAILED':
      title = cy.state === 'FAILED' ? 'Something failed' : 'Round on hold';
      body = <>{lastReason(cy) ?? info.hint} {org && cy.prior_state ? `Resuming returns it to “${stateInfo(cy.prior_state).label}”.` : ''}</>;
      if (org && cy.prior_state) actions = <Button icon="play" onClick={() => setReasonOpen(true)}>Resume round</Button>;
      break;
    case 'DISPUTED':
      title = 'Dispute open';
      body = <>{lastReason(cy) ?? info.hint} The ledger is unchanged; the organizer records a resolution.</>;
      if (org) actions = <Button icon="check" onClick={() => setReasonOpen(true)}>Resolve dispute</Button>;
      break;
    default:
      break;
  }

  return (
    <Card className="next-step" title={<span className="row"><Icon name="sparkles" width={18} height={18} /> {title}</span>}>
      <p>{body}</p>
      {cy.state === 'AUCTION_OPEN' && c.my_member_id && <BidForm c={c} cy={cy} bids={bids} onPlaced={onChanged} />}
      {actions && <div className="next-step__actions">{actions}</div>}
      {act.error && <Banner tone="danger">{act.error}</Banner>}
      <ReasonModal open={reasonOpen} onClose={() => setReasonOpen(false)}
        title={cy.state === 'DISPUTED' ? 'Resolve dispute' : 'Resume round'}
        label={cy.state === 'DISPUTED' ? 'Resolution' : 'Why is it safe to continue?'}
        onSubmit={async (reason) => {
          await (cy.state === 'DISPUTED' ? api.resolveDispute(session, cy.id, reason) : api.resume(session, cy.id, reason));
          toast(cy.state === 'DISPUTED' ? 'Dispute resolved' : 'Round resumed');
          onChanged();
        }} />
    </Card>
  );
}

const lastReason = (cy: CycleView) => [...cy.transitions].reverse().find((t) => t.to === cy.state)?.reason ?? null;

function ReasonModal({ open, onClose, title, label, onSubmit, danger }: {
  open: boolean; onClose: () => void; title: string; label: string; onSubmit: (reason: string) => Promise<void>; danger?: boolean;
}) {
  const [reason, setReason] = useState('');
  const submit = useAction(async () => { await onSubmit(reason.trim()); setReason(''); onClose(); });
  return (
    <Modal open={open} title={title} onClose={onClose} footer={<>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button variant={danger ? 'danger' : 'primary'} disabled={!reason.trim() || submit.pending} onClick={() => void submit.run()}>
        {submit.pending ? 'Saving…' : 'Confirm'}</Button>
    </>}>
      <Field label={label} help="Recorded permanently in the round’s history.">
        {(id) => <textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      {submit.error && <Banner tone="danger">{submit.error}</Banner>}
    </Modal>
  );
}

// ------------------------------------------------------------------ bidding
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = window.setTimeout(() => setV(value), ms); return () => window.clearTimeout(t); }, [value, ms]);
  return v;
}

function BidForm({ c, cy, bids, onPlaced }: { c: CircleView; cy: CycleView; bids: BidView[] | undefined; onPlaced: () => void }) {
  const session = useSession();
  const toast = useToast();
  const me = c.members.find((m) => m.id === c.my_member_id)!;
  const [raw, setRaw] = useState('');
  const [minor, setMinor] = useState<number | null>(null);
  const debounced = useDebounced(minor, 350);
  const preview = useApi(debounced ? `preview:${cy.id}:${debounced}` : null,
    (s) => api.bidPreview(session, cy.id, me.id, debounced!, s), { refetchOnFocus: false });
  const place = useAction(async () => {
    const res = await api.submitBid(session, cy.id, me.id, minor!);
    if (res.accepted) { toast('Bid placed'); setRaw(''); setMinor(null); onPlaced(); }
    else throw new Error(`Bid not accepted: ${res.reasons.map(reasonLabel).join(' ')}`);
  });

  if (me.has_won) return <Banner tone="neutral">You already received a pot in this circle, so you can’t bid again.</Banner>;
  const mine = bids?.find((b) => b.member_id === me.id && b.accepted);
  if (mine && c.ruleset.payout_mode === 'SEALED_BID_AUCTION') {
    return (
      <Banner tone="success" icon="lock" title="Your sealed bid is in">
        You bid <Amount minor={mine.discount} currency={cy.currency} />. It stays hidden from others until the organizer closes the auction.
      </Banner>
    );
  }
  const p = preview.data;
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); if (minor) void place.run(); }}>
      <Field label="Your discount bid" help="How much of the pot you’re willing to give up to receive it this round.">
        {(id) => <MoneyInput id={id} currency={cy.currency} value={raw} placeholder="e.g. 12,000"
                             onChange={(r, m) => { setRaw(r); setMinor(m); }} invalid={!!raw && minor === null} />}
      </Field>
      {p && (
        <div className="stack stack--sm">
          <div className="bid-preview">
            <div><Stat label="You would receive"><Amount minor={p.preview?.you_receive_minor} currency={cy.currency} tone="income" size="md" /></Stat></div>
            <div><Stat label="Discount" hint={`${p.discount_rate} of the pot`}><Amount minor={p.discount_minor} currency={cy.currency} size="md" /></Stat></div>
            <div><Stat label="Dividend to members"><Amount minor={p.preview?.dividend_pool_minor} currency={cy.currency} /></Stat></div>
            <div><Stat label="Maximum allowed"><Amount minor={p.cap_minor} currency={cy.currency} /></Stat></div>
          </div>
          {p.reasons.filter((r) => r !== 'AUCTION_NOT_OPEN').length > 0 && (
            <Banner tone="warning">{p.reasons.map(reasonLabel).join(' ')}</Banner>
          )}
          <p className="muted small">
            <Icon name="bot" width={13} height={13} /> Bid advisor: {p.history.length
              ? <>past winning discounts here were {p.history.map((h) => `${h.discount_rate} (R${h.cycle_number})`).join(', ')}. </> : null}
            {p.note}
          </p>
        </div>
      )}
      <div className="row row--wrap">
        <Button type="submit" icon="gavel" disabled={!minor || place.pending || (p ? !p.valid : false)}>{place.pending ? 'Placing…' : 'Place bid'}</Button>
        {isAuction(cy.payout_mode) && c.ruleset.payout_mode === 'SEALED_BID_AUCTION' && <span className="muted small"><Icon name="lock" width={13} height={13} /> Sealed: others see your bid only after the auction closes. One bid per member.</span>}
      </div>
      {place.error && <Banner tone="danger">{place.error}</Banner>}
    </form>
  );
}

function Bids({ c, cy, bids, nameOf }: { c: CircleView; cy: CycleView; bids: ApiState<BidView[]>; nameOf: (id: string | null) => string }) {
  return (
    <Card title="Bids" subtitle={c.ruleset.payout_mode === 'SEALED_BID_AUCTION' && cy.state === 'AUCTION_OPEN' ? 'Sealed until the auction closes.' : undefined}>
      <DataBoundary state={bids} skeleton={<Skeleton kind="line" count={3} />}>
        {(list) => list.length === 0 ? <p className="muted">No bids yet.</p> : (
          <ul className="list">
            {[...list].sort((a, b) => (b.discount ?? -1) - (a.discount ?? -1)).map((b) => (
              <li key={b.bid_id} className="list__row">
                <Avatar name={nameOf(b.member_id)} small you={b.member_id === c.my_member_id} />
                <div className="grow">
                  <div className="list__title">{nameOf(b.member_id)}{b.member_id === c.my_member_id && <span className="muted">(you)</span>}
                    {b.member_id === cy.winner_member_id && b.accepted && <Pill tone="brand" icon="trophy">Winner</Pill>}</div>
                  <div className="muted small">{formatDateTime(b.submitted_at)}{!b.accepted && b.reasons?.length ? ` · ${b.reasons.map(reasonLabel).join(' ')}` : ''}</div>
                </div>
                {b.discount === null ? <Pill icon="lock">Sealed</Pill>
                  : <span className="right"><Amount minor={b.discount} currency={cy.currency} tone={b.accepted ? 'default' : 'muted'} />
                    {!b.accepted && <div><Pill tone="danger">Rejected</Pill></div>}</span>}
              </li>
            ))}
          </ul>
        )}
      </DataBoundary>
    </Card>
  );
}

// ------------------------------------------------------------------ contributions
function Contributions({ c, cy, config, nameOf, onChanged }: {
  c: CircleView; cy: CycleView; config: AppConfigView | undefined; nameOf: (id: string | null) => string; onChanged: () => void;
}) {
  const session = useSession();
  const toast = useToast();
  const org = c.my_role === 'organizer';
  const open = paymentOpen(cy.payout_mode, cy);
  const settled = cy.obligations.filter((o) => o.outstanding === 0).length;
  const [link, setLink] = useState<{ name: string; url: string | null; detail: string } | null>(null);
  const pay = useAction(async (o: ObligationView, how: 'sandbox' | 'paypal') => {
    if (how === 'sandbox') {
      await api.sandboxPayment(session, cy.id, o.member_id);
      toast(`Payment confirmed for ${nameOf(o.member_id)} (sandbox)`);
      onChanged();
    } else {
      const res = await api.createCollection(session, cy.id, o.member_id);
      if (o.member_id === c.my_member_id && res.approval_url) window.open(res.approval_url, '_blank', 'noopener');
      setLink({ name: nameOf(o.member_id), url: res.approval_url, detail: res.detail });
    }
  });

  if (cy.obligations.length === 0) {
    return <Card title="Contributions"><p className="muted">Obligations are created when the organizer opens collections.</p></Card>;
  }
  const mine = cy.obligations.find((o) => o.member_id === c.my_member_id);
  const rows = org ? cy.obligations : cy.obligations.filter((o) => o.member_id === c.my_member_id);
  const paypal = config?.payment_gateway === 'paypal';

  return (
    <Card title="Contributions" subtitle={`${settled} of ${cy.obligations.length} members confirmed`}>
      <ProgressBar value={settled} max={cy.obligations.length} tone="income" />
      {!open && cy.state !== 'FINALIZED' && (
        <Banner tone="info">{isAuction(cy.payout_mode)
          ? 'Installments are finalized after the auction settles (each member’s dividend lowers it). Payments open then.'
          : 'Payments open once collections are open.'}</Banner>
      )}
      {mine && open && mine.outstanding > 0 && (
        <div className="card card--warning" style={{ boxShadow: 'none' }}>
          <div className="row row--between row--wrap">
            <div><p className="small">You owe this round</p><Amount minor={mine.outstanding} currency={cy.currency} size="lg" /></div>
            <div className="row row--wrap">
              {paypal && <Button icon="external" disabled={pay.pending} onClick={() => void pay.run(mine, 'paypal')}>Pay with PayPal</Button>}
              {config?.sandbox_tools && <Button variant={paypal ? 'secondary' : 'primary'} icon="check" disabled={pay.pending}
                onClick={() => void pay.run(mine, 'sandbox')}>Simulate confirmed payment</Button>}
            </div>
          </div>
          <p className="small">A contribution counts only after the payment provider confirms it.{config?.sandbox_tools && ' Sandbox simulation runs the same confirmation pipeline, labelled as a sandbox event.'}</p>
        </div>
      )}
      {pay.error && <Banner tone="danger">{pay.error}</Banner>}
      {link && (
        <Banner tone={link.url ? 'success' : 'warning'} title={`PayPal invoice for ${link.name}`}
                action={<button type="button" className="link" onClick={() => setLink(null)}>Dismiss</button>}>
          {link.url ? <a className="link" href={link.url} target="_blank" rel="noreferrer">Open payment page <Icon name="external" /></a> : link.detail}
        </Banner>
      )}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Member</th><th className="num">Net due</th><th className="num">Confirmed</th><th className="num">Outstanding</th><th>Status</th>{org && open && <th />}</tr></thead>
          <tbody>
            {rows.map((o) => {
              const done = o.outstanding === 0;
              const late = !done && new Date(cy.due_date).getTime() < Date.now();
              return (
                <tr key={o.member_id} className={o.member_id === c.my_member_id ? 'is-you' : undefined}>
                  <td><span className="row"><Avatar name={nameOf(o.member_id)} small />{nameOf(o.member_id)}</span></td>
                  <td className="num"><Amount minor={o.net_payable} currency={cy.currency} /></td>
                  <td className="num"><Amount minor={o.confirmed_paid} currency={cy.currency} tone={o.confirmed_paid ? 'income' : 'muted'} /></td>
                  <td className="num"><Amount minor={o.outstanding} currency={cy.currency} tone={done ? 'muted' : 'warning'} /></td>
                  <td>{done ? <Pill tone="success" icon="check">Paid</Pill> : late ? <Pill tone="danger">Late</Pill> : <Pill tone="warning">Due</Pill>}</td>
                  {org && open && (
                    <td className="right">{!done && (
                      <span className="row" style={{ justifyContent: 'flex-end' }}>
                        {config?.sandbox_tools && <Button variant="soft" small disabled={pay.pending} onClick={() => void pay.run(o, 'sandbox')}>Record (sandbox)</Button>}
                        {paypal && <Button variant="ghost" small icon="send" disabled={pay.pending} onClick={() => void pay.run(o, 'paypal')}>Invoice</Button>}
                      </span>
                    )}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!org && <p className="muted small">Other members’ payment details are private; the progress bar shows the group status.</p>}
    </Card>
  );
}

// ------------------------------------------------------------------ side panels
function Explanation({ c, cy }: { c: CircleView; cy: CycleView }) {
  const session = useSession();
  const mine = cy.obligations.find((o) => o.member_id === c.my_member_id);
  const ex = useApi(`explain:${sessionKey(session)}:${cy.id}:${cy.settlement_id ?? ''}:${mine?.confirmed_paid ?? 0}`,
    (s) => api.explain(session, cy.id, c.my_member_id!, s));
  return (
    <Card title={<span className="row"><Icon name="sparkles" width={16} height={16} /> Why is my installment this amount?</span>}
          subtitle="Built from the stored settlement and ledger, not estimated.">
      <DataBoundary state={ex} skeleton={<Skeleton kind="line" count={4} />}>
        {(e) => (
          <>
            <div className="explain-lines">
              {e.lines.map((l) => (
                <div key={l.label}>
                  <span>{l.label}{l.note && <small>{l.note}</small>}</span>
                  <Amount minor={l.amount_minor} currency={e.currency} tone={l.amount_minor < 0 ? 'income' : 'default'} />
                </div>
              ))}
            </div>
            <p className="muted small">{e.summary}</p>
          </>
        )}
      </DataBoundary>
    </Card>
  );
}

function History({ cy }: { cy: CycleView }) {
  if (!cy.transitions.length) return null;
  return (
    <Card title="Round history">
      <ul className="list">
        {[...cy.transitions].reverse().map((t, i) => (
          <li key={i} className="list__row">
            <div className="grow">
              <div className="list__title small">{stateInfo(t.to).label}</div>
              <div className="muted small">{formatDateTime(t.at)} · {t.actor === 'system' || t.actor === 'provider' ? humanize(t.actor) : 'by a person'}</div>
              {t.reason && <div className="small">{t.reason}</div>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Dispute({ c, cy, onChanged }: { c: CircleView; cy: CycleView; onChanged: () => void }) {
  const session = useSession();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  if (cy.state === 'FINALIZED' || cy.state === 'DISPUTED' || c.my_role === 'none') return null;
  return (
    <Card title="Something looks wrong?" subtitle="Flag it. The organizer reviews it and the original records are never edited.">
      <Button variant="secondary" small icon="flag" onClick={() => setOpen(true)}>Flag a problem</Button>
      <ReasonModal open={open} onClose={() => setOpen(false)} title="Flag a problem" label="What doesn’t look right?" danger
        onSubmit={async (reason) => { await api.openDispute(session, cy.id, reason); toast('Dispute opened', 'info'); onChanged(); }} />
    </Card>
  );
}
