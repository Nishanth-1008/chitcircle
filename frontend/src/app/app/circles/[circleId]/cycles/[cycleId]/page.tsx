'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { ActivityRow, DataBoundary, RoundStepper, StateBadge, useExpandable } from '@/components/domain';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Amount, Avatar, Banner, Button, ErrorState, SectionHead, Skeleton, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { resolveCurrency } from '@/lib/api/currency';
import { memberName, myObligation, settledCount } from '@/lib/derive';
import { dueLabel, formatDate, formatDateTime } from '@/lib/format';
import { useApi, useSingleFlight } from '@/lib/hooks';
import { findSettlementId, sortLedger } from '@/lib/ledger';
import { roleIn } from '@/lib/permissions';
import { useSaved } from '@/lib/saved';
import { sessionKey, useSession } from '@/lib/session';
import { AUCTION_REJECT_REASONS, humanize, isExceptionState, stateInfo } from '@/lib/status';
import { PAYOUT_GATEWAY } from '@/lib/config';

export default function RoundPage() {
  const { circleId, cycleId } = useParams<{ circleId: string; cycleId: string }>();
  const ctx = useSession();
  const saved = useSaved(ctx.mode);
  const { open, toggle } = useExpandable();
  const k = sessionKey(ctx);

  const cycle = useApi(`cycle:${k}:${cycleId}`, (s) => api.getCycle(ctx, cycleId, s));
  const circle = useApi(`circle:${k}:${circleId}`, (s) => api.getCircle(ctx, circleId, s));
  const ledger = useApi(`ledger:${k}:${cycleId}`, (s) => api.getLedger(ctx, cycleId, s));
  const showBids = cycle.data ? ['AUCTION_OPEN', 'AUCTION_CLOSED'].includes(cycle.data.state) || cycle.data.payout_method?.includes('AUCTION') : false;
  const bids = useApi(showBids ? `bids:${k}:${cycleId}` : null, (s) => api.listBids(ctx, cycleId, s));

  useEffect(() => {
    if (cycle.data && cycle.data.circle_id === circleId) saved.saveRound(cycle.data.id, circleId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cycle.data?.id]);

  const currency = useMemo(() => resolveCurrency({ ledger: ledger.data }), [ledger.data]);
  const settlementId = findSettlementId(ledger.data);

  const mismatch = cycle.data && cycle.data.circle_id !== circleId;
  const role = roleIn(circle.data, ctx.actor);
  const member = circle.data?.members.find((m) => m.id === ctx.actor?.id);
  const hasWon = !!member?.has_won;
  const live = ctx.mode === 'live';

  const [openCycleMsg, setOpenCycleMsg] = useState('');
  const [openAuctionMsg, setOpenAuctionMsg] = useState('');
  const [closeAuctionMsg, setCloseAuctionMsg] = useState('');
  const [selectRecipientMsg, setSelectRecipientMsg] = useState('');
  const [calculateSettlementMsg, setCalculateSettlementMsg] = useState('');
  const [bidDiscount, setBidDiscount] = useState('');
  const [bidError, setBidError] = useState('');
  const [collectionMsg, setCollectionMsg] = useState('');

  const openCycleAction = useSingleFlight(async () => {
    setOpenCycleMsg('');
    try {
      await api.openCycle(ctx, cycleId);
      setOpenCycleMsg('Round opened for collections.');
    } catch (e) { setOpenCycleMsg(describeError(e).message); }
  });

  const submitCollectionAction = useSingleFlight(async () => {
    setCollectionMsg('');
    const m = circle.data?.members.find((mm) => mm.id === ctx.actor?.id);
    if (!m) { setCollectionMsg('You are not a member of this circle.'); return; }
    try {
      await api.createCollection(ctx, cycleId, m.id);
      setCollectionMsg('Payment request created. Complete it on PayPal.');
    } catch (e) { setCollectionMsg(describeError(e).message); }
  });

  const openAuctionAction = useSingleFlight(async () => {
    setOpenAuctionMsg('');
    try {
      await api.openAuction(ctx, cycleId);
      setOpenAuctionMsg('Auction opened.');
    } catch (e) { setOpenAuctionMsg(describeError(e).message); }
  });

  const closeAuctionAction = useSingleFlight(async () => {
    setCloseAuctionMsg('');
    try {
      await api.closeAuction(ctx, cycleId);
      setCloseAuctionMsg('Auction closed.');
    } catch (e) { setCloseAuctionMsg(describeError(e).message); }
  });

  const selectRecipientAction = useSingleFlight(async () => {
    setSelectRecipientMsg('');
    try {
      await api.selectRecipient(ctx, cycleId);
      setSelectRecipientMsg('Recipient selected.');
    } catch (e) { setSelectRecipientMsg(describeError(e).message); }
  });

  const calculateSettlementAction = useSingleFlight(async () => {
    setCalculateSettlementMsg('');
    try {
      await api.calculateSettlement(ctx, cycleId);
      setCalculateSettlementMsg('Settlement calculated.');
    } catch (e) { setCalculateSettlementMsg(describeError(e).message); }
  });

  const submitBidAction = useSingleFlight(async () => {
    setBidError('');
    const discount = Math.round(Number(bidDiscount) * 100);
    if (!Number.isFinite(discount) || discount < 0) { setBidError('Enter a valid discount.'); return; }
    try {
      await api.submitBid(ctx, cycleId, { member_id: ctx.actor!.id, discount });
      setBidDiscount('');
      setBidError('');
    } catch (e) { setBidError(describeError(e).message); }
  });

  return (
    <Screen title={cycle.data ? `Round ${cycle.data.number}` : 'Round'} back={`/app/circles/${encodeURIComponent(circleId)}`}>
      {mismatch && <ErrorState error={new Error('This round belongs to a different circle.')} />}
      {!mismatch && (
        <DataBoundary state={cycle} skeleton={<Skeleton count={3} />}>
          {(c) => {
            const info = stateInfo(c.state);
            const role = roleIn(circle.data, ctx.actor);
            const mine = myObligation(c, ctx.actor);
            const total = c.obligations?.length ?? 0;
            const events = ledger.data ? sortLedger(ledger.data) : [];
            const nameOf = (id: string | null) => memberName(circle.data, id);
            return (
              <>
                <section className="card stack" aria-label="Round status">
                  <div className="row row--between">
                    <div>
                      <p className="circle-card__name">{circle.data?.name ?? 'Circle'}</p>
                      <p className="muted">Due {formatDate(c.due_date)} · {dueLabel(c.due_date)}</p>
                    </div>
                    <StateBadge state={c.state} />
                  </div>
                  <RoundStepper state={c.state} priorState={c.prior_state} />
                  <p className="muted">{info.hint}</p>
                </section>

                {isExceptionState(c.state) && (
                  <Banner tone="danger" icon="alert">
                    This round is {info.label.toLowerCase()}{c.prior_state ? ` (it was ${stateInfo(c.prior_state).label.toLowerCase()} before)` : ''}. Only the organizer can resolve it, through the server.
                  </Banner>
                )}
                {c.state === 'PAYOUT_PENDING' || c.state === 'PAYOUT_SUBMITTED' || c.state === 'PAYOUT_CONFIRMED' || c.state === 'RECONCILIATION_PENDING' || c.state === 'FINALIZED' ? (
                  PAYOUT_GATEWAY === 'stub' && ctx.mode === 'live' && (
                    <Banner tone="warning" icon="alert">The payout gateway is a stub in this backend build. A payout status here does not mean real funds moved.</Banner>
                  )
                ) : null}

                {mine && (
                  <section className="card stack" aria-label="Your contribution">
                    <SectionHead title="Your contribution" action={
                      <StatusPill tone={mine.outstanding === 0 ? 'success' : 'warning'} icon={mine.outstanding === 0 ? 'check' : 'clock'}>
                        {mine.outstanding === 0 ? 'Settled' : 'Outstanding'}
                      </StatusPill>} />
                    <div className="stats">
                      <div><div className="stat__label">Net due</div><div className="stat__value"><Amount minor={mine.net_payable} currency={currency.code} assumed={currency.assumed && ctx.mode === 'live'} /></div></div>
                      <div><div className="stat__label">Confirmed paid</div><div className="stat__value"><Amount minor={mine.confirmed_paid} currency={currency.code} assumed={false} tone={mine.confirmed_paid > 0 ? 'income' : 'default'} /></div></div>
                      <div><div className="stat__label">Outstanding</div><div className="stat__value"><Amount minor={mine.outstanding} currency={currency.code} tone={mine.outstanding > 0 ? 'warning' : 'income'} /></div></div>
                    </div>
                    {mine.outstanding > 0 && <p className="muted">Online payment isn’t connected yet. A contribution counts only after the payment provider confirms it.</p>}
                  </section>
                )}

                {live && mine && role === 'member' && mine.outstanding > 0 && !hasWon && (
                  <section className="card stack" aria-label="Pay your contribution">
                    <SectionHead title="Pay your contribution" />
                    <p className="muted">Create a PayPal payment request for your outstanding contribution. You’ll complete the payment on PayPal’s site.</p>
                    {collectionMsg && <Banner tone="info">{collectionMsg}</Banner>}
                    <Button variant="primary" disabled={submitCollectionAction.pending} onClick={() => void submitCollectionAction.run()}>
                      {submitCollectionAction.pending ? 'Creating…' : 'Pay Contribution'}
                    </Button>
                  </section>
                )}

                {c.winner_member_id && (
                  <section className="card row" aria-label="Recipient">
                    <span className="glyph glyph--income"><Icon name="trophy" /></span>
                    <div className="grow">
                      <p className="muted">Recipient this round</p>
                      <p style={{ fontWeight: 700 }}>{nameOf(c.winner_member_id)}</p>
                    </div>
                    {c.discount !== null && (
                      <div style={{ textAlign: 'right' }}>
                        <p className="muted" style={{ fontSize: 12 }}>Winning discount</p>
                        <Amount minor={c.discount} currency={currency.code} />
                      </div>
                    )}
                  </section>
                )}

                {settlementId ? (
                  <Link href={`/app/settlements/${encodeURIComponent(settlementId)}`} className="card row" aria-label="Review settlement">
                    <span className="glyph"><Icon name="scale" /></span>
                    <div className="grow"><strong>Review settlement</strong><p className="muted">{info.settlementLabel}</p></div>
                    <Icon name="chevronRight" width={18} height={18} />
                  </Link>
                ) : ledger.error && !ledger.data ? null : null}

                {bids.data && bids.data.length > 0 && (
                  <section className="card" aria-label="Auction bids">
                    <SectionHead title="Bids" />
                    <ul>
                      {bids.data.map((b) => (
                        <li key={b.bid_id} className="listrow">
                          <Avatar name={nameOf(b.member_id)} small />
                          <div className="grow">
                            <div style={{ fontWeight: 600 }}>{nameOf(b.member_id)}</div>
                            {!b.accepted && b.reasons && b.reasons.length > 0 && (
                              <div className="field__error">Rejected: {b.reasons.map((r) => AUCTION_REJECT_REASONS[r] ?? humanize(r)).join(' ')}</div>)}
                          </div>
                          {b.sealed || b.discount === null
                            ? <StatusPill icon="lock">Sealed</StatusPill>
                            : <Amount minor={b.discount} currency={currency.code} />}
                        </li>
                      ))}
                    </ul>
                    <p className="muted" style={{ marginTop: 8 }}>The server validates bids and decides the winner.</p>
                  </section>
                )}

                {total > 0 && (
                  <section className="card" aria-label="Contributions">
                    <SectionHead title="Contributions" action={<span className="muted num">{settledCount(c)} of {total} settled</span>} />
                    <ul>
                      {c.obligations!.map((o) => (
                        <li key={o.member_id} className="listrow">
                          <Avatar name={nameOf(o.member_id)} small />
                          <div className="grow" style={{ fontWeight: 600 }}>{nameOf(o.member_id)}{o.member_id === ctx.actor?.id && <span className="muted"> (you)</span>}</div>
                          {role === 'organizer' && o.outstanding > 0 && <Amount minor={o.outstanding} currency={currency.code} tone="warning" />}
                          <StatusPill tone={o.outstanding === 0 ? 'success' : 'warning'}>{o.outstanding === 0 ? 'Settled' : 'Outstanding'}</StatusPill>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="card" aria-label="Recent activity">
                  <SectionHead title="Activity" action={<Link className="link" href={`/app/activity?round=${encodeURIComponent(cycleId)}`}>See all</Link>} />
                  {ledger.loading && !ledger.data && <Skeleton kind="line" count={3} />}
                  {ledger.error && !ledger.data && <ErrorState error={ledger.error} onRetry={ledger.refetch} compact />}
                  {ledger.data && events.length === 0 && <p className="muted">No ledger entries yet.</p>}
                  <ul className="activity">
                    {events.slice(0, 4).map((e) => (
                      <ActivityRow key={e.id} event={e} memberById={(id) => circle.data?.members.find((m) => m.id === id)}
                                   demo={ctx.mode === 'demo'} expanded={open === e.id} onToggle={() => toggle(e.id)} />
                    ))}
                  </ul>
                </section>

                {c.transitions && c.transitions.length > 0 && (
                  <details className="card">
                    <summary style={{ fontWeight: 600, minHeight: 44, display: 'flex', alignItems: 'center' }}>Round history</summary>
                    <ol className="timeline" style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
                      {c.transitions.map((t, i) => (
                        <li key={i}><div>
                          <strong>{stateInfo(t.to).label}</strong>
                          <small>{formatDateTime(t.at)} · by {t.actor}{t.reason ? ` · ${t.reason}` : ''}</small>
                        </div></li>
                      ))}
                    </ol>
                  </details>
                )}

                {live && c.state === 'DRAFT' && role === 'organizer' && (
                  <section className="card stack" aria-label="Start collections">
                    <SectionHead title="Start collections" />
                    <p className="muted">Open this round so members can begin contributing.</p>
                    {openCycleMsg && <Banner tone="info">{openCycleMsg}</Banner>}
                    <Button variant="primary" disabled={openCycleAction.pending} onClick={() => void openCycleAction.run()}>
                      {openCycleAction.pending ? 'Opening…' : 'Start Collections'}
                    </Button>
                  </section>
                )}

                {live && c.state === 'COLLECTIONS_IN_PROGRESS' && role === 'organizer' && (
                  <section className="card stack" aria-label="Open auction">
                    <SectionHead title="Open auction" />
                    <p className="muted">Move this round to auction so members can place bids.</p>
                    {openAuctionMsg && <Banner tone="info">{openAuctionMsg}</Banner>}
                    <Button variant="primary" disabled={openAuctionAction.pending} onClick={() => void openAuctionAction.run()}>
                      {openAuctionAction.pending ? 'Opening…' : 'Open Auction'}
                    </Button>
                  </section>
                )}

                {live && c.state === 'AUCTION_OPEN' && role === 'organizer' && (
                  <section className="card stack" aria-label="Close auction">
                    <SectionHead title="Close auction" />
                    <p className="muted">Close bidding and let the server determine the winner.</p>
                    {closeAuctionMsg && <Banner tone="info">{closeAuctionMsg}</Banner>}
                    <Button variant="primary" disabled={closeAuctionAction.pending} onClick={() => void closeAuctionAction.run()}>
                      {closeAuctionAction.pending ? 'Closing…' : 'Close Auction'}
                    </Button>
                  </section>
                )}

                {live && c.state === 'AUCTION_OPEN' && role === 'member' && !hasWon && (
                  <section className="card stack" aria-label="Place your bid">
                    <SectionHead title="Place your bid" />
                    <p className="muted">Enter the discount you want to bid. The server validates bids and decides the winner.</p>
                    <form className="stack" onSubmit={(e) => { e.preventDefault(); void submitBidAction.run(); }} noValidate>
                      <div className="field">
                        <label htmlFor="bid-discount">Discount (minor units)</label>
                        <input id="bid-discount" type="number" value={bidDiscount} onChange={(e) => { setBidDiscount(e.target.value); setBidError(''); }} />
                        <span className="field__help">Whole minor units (e.g. 400000 for ₹4,00,000 off).</span>
                      </div>
                      {bidError && <Banner tone="danger">{bidError}</Banner>}
                      <Button block type="submit" disabled={submitBidAction.pending}>{submitBidAction.pending ? 'Bidding…' : 'Place Bid'}</Button>
                    </form>
                  </section>
                )}

                {live && c.state === 'AUCTION_CLOSED' && role === 'organizer' && (
                  <section className="card stack" aria-label="Select recipient">
                    <SectionHead title="Select recipient" />
                    <p className="muted">Choose the auction winner who receives the payout this round.</p>
                    {selectRecipientMsg && <Banner tone="info">{selectRecipientMsg}</Banner>}
                    <Button variant="primary" disabled={selectRecipientAction.pending} onClick={() => void selectRecipientAction.run()}>
                      {selectRecipientAction.pending ? 'Selecting…' : 'Select Recipient'}
                    </Button>
                  </section>
                )}

                {live && c.state === 'SETTLEMENT_CALCULATED' && role === 'organizer' && (
                  <section className="card stack" aria-label="Calculate settlement">
                    <SectionHead title="Calculate settlement" />
                    <p className="muted">Confirm the settlement figures before they go to approval.</p>
                    {calculateSettlementMsg && <Banner tone="info">{calculateSettlementMsg}</Banner>}
                    <Button variant="primary" disabled={calculateSettlementAction.pending} onClick={() => void calculateSettlementAction.run()}>
                      {calculateSettlementAction.pending ? 'Calculating…' : 'Calculate Settlement'}
                    </Button>
                  </section>
                )}
              </>
            );
          }}
        </DataBoundary>
      )}
    </Screen>
  );
}
