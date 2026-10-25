'use client';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Icon, type IconName } from '@/components/Icon';
import { ActivityRow, CircleCard, DataBoundary, DueCard, useExpandable } from '@/components/domain';
import { OpenCircleSheet } from '@/components/OpenCircleSheet';
import { Screen } from '@/components/shell';
import { Avatar, Banner, Button, EmptyState, SectionHead, Skeleton } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { resolveCurrency } from '@/lib/api/currency';
import { myObligation } from '@/lib/derive';
import { sortLedger } from '@/lib/ledger';
import { useApi } from '@/lib/hooks';
import { useOverviews, type OverviewItem } from '@/lib/overview';
import { roleIn } from '@/lib/permissions';
import { useSaved } from '@/lib/saved';
import { sessionKey, useSession } from '@/lib/session';
import { stateInfo } from '@/lib/status';

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

interface ActionItem { id: string; icon: IconName; title: string; body: string; href: string }

function actionItems(items: OverviewItem[], actor: ReturnType<typeof useSession>['actor']): ActionItem[] {
  const out: ActionItem[] = [];
  for (const it of items) {
    if (!it.circle || !it.round) continue;
    const href = `/app/circles/${encodeURIComponent(it.circle.id)}/cycles/${encodeURIComponent(it.round.id)}`;
    const role = roleIn(it.circle, actor);
    const s = it.round.state;
    const body = `${it.circle.name} · Round ${it.round.number}`;
    if (s === 'AUCTION_OPEN') out.push({ id: `${it.round.id}-auc`, icon: 'gavel', title: 'Auction is open', body, href });
    else if (s === 'AWAITING_APPROVAL' && role === 'organizer') out.push({ id: `${it.round.id}-app`, icon: 'scale', title: 'Settlement awaiting approval', body, href });
    else if (s === 'ON_HOLD' || s === 'FAILED' || s === 'DISPUTED') out.push({ id: `${it.round.id}-att`, icon: 'alert', title: `Round ${stateInfo(s).label.toLowerCase()}`, body: `${it.circle.name} needs attention`, href });
  }
  return out.slice(0, 2);
}

export default function HomePage() {
  const ctx = useSession();
  const saved = useSaved(ctx.mode);
  const overview = useOverviews(ctx, saved.items);
  const [sheet, setSheet] = useState(false);
  const { open, toggle } = useExpandable();
  const assumed = ctx.mode === 'live';
  const currency = resolveCurrency().code;

  const loaded = useMemo(() => (overview.data ?? []).filter((i) => i.circle), [overview.data]);
  const due = useMemo(() => loaded
    .map((it) => ({ it, mine: myObligation(it.round, ctx.actor) }))
    .filter((x) => x.it.round && x.mine && x.mine.outstanding > 0 && x.it.round.state !== 'FINALIZED')
    .sort((a, b) => a.it.round!.due_date.localeCompare(b.it.round!.due_date))[0], [loaded, ctx.actor]);
  const featured = loaded.find((i) => i.round && i !== due?.it) ?? due?.it ?? loaded[0];
  const actions = useMemo(() => actionItems(loaded, ctx.actor), [loaded, ctx.actor]);

  const focus = due?.it ?? featured;
  const ledger = useApi(focus?.round ? `home-ledger:${sessionKey(ctx)}:${focus.round.id}` : null,
    (signal) => api.getLedger(ctx, focus!.round!.id, signal));
  const memberById = (id: string | null) => focus?.circle?.members.find((m) => m.id === id);

  return (
    <Screen brand right={<Link href="/app/profile" aria-label="Profile"><Avatar name={ctx.actor?.displayName ?? ctx.actor?.id ?? '?'} /></Link>}>
      <div className="greeting">
        <div className="grow">
          <h1>{greeting()}{ctx.actor?.displayName ? `, ${ctx.actor.displayName}` : ''}</h1>
          <p className="muted">{saved.items.circles.length === 0 ? 'Open a circle to get started' : `${saved.items.circles.length} circle${saved.items.circles.length === 1 ? '' : 's'} saved on this device`}</p>
        </div>
      </div>

      <Button block icon="plus" onClick={() => setSheet(true)}>Open a circle</Button>

      <div className="tiles">
        <Link href="/app/circles" className="tile"><span className="tile__icon"><Icon name="circles" /></span>My circles</Link>
        <Link href="/app/activity" className="tile"><span className="tile__icon"><Icon name="activity" /></span>Activity</Link>
      </div>

      {saved.items.circles.length === 0 && (
        <EmptyState icon="circles" title="No circles yet" action={<Button onClick={() => setSheet(true)}>Open a circle</Button>}>
          The backend can’t list your circles yet, so add one with its circle ID.
        </EmptyState>
      )}

      {saved.items.circles.length > 0 && (
        <DataBoundary state={overview} skeleton={<Skeleton count={3} />}>
          {() => (
            <>
              {due?.it.round && due.it.circle && (
                <DueCard circleName={due.it.circle.name} circleId={due.it.circle.id} round={due.it.round}
                         mineOutstanding={due.mine!.outstanding} currency={currency} assumed={assumed} />
              )}

              {actions.length > 0 && (
                <section className="stack" aria-label="Needs your attention">
                  <SectionHead title="Needs your attention" />
                  {actions.map((a) => (
                    <Link key={a.id} href={a.href} className="card action-item">
                      <span className="glyph glyph--warning"><Icon name={a.icon} /></span>
                      <span className="grow"><strong>{a.title}</strong><span className="muted" style={{ display: 'block' }}>{a.body}</span></span>
                      <Icon name="chevronRight" width={18} height={18} />
                    </Link>
                  ))}
                </section>
              )}

              {featured?.circle && (
                <section className="stack" aria-label="Featured circle">
                  <SectionHead title="Your circles" action={<Link className="link" href="/app/circles">View all</Link>} />
                  <CircleCard item={featured} actor={ctx.actor} currency={currency} assumed={assumed} />
                </section>
              )}

              {ledger.data && ledger.data.length > 0 && (
                <section className="card" aria-label="Recent activity">
                  <SectionHead title="Recent activity" action={<Link className="link" href="/app/activity">See all</Link>} />
                  <ul className="activity">
                    {sortLedger(ledger.data).slice(0, 3).map((e) => (
                      <ActivityRow key={e.id} event={e} memberById={memberById} demo={ctx.mode === 'demo'}
                                   expanded={open === e.id} onToggle={() => toggle(e.id)} />
                    ))}
                  </ul>
                </section>
              )}
              {loaded.length === 0 && (
                <Banner tone="warning" icon="alert">None of your saved circles could be loaded. Open the Circles tab to see why.</Banner>
              )}
            </>
          )}
        </DataBoundary>
      )}
      <Banner tone="neutral" icon="info">Home shows circles saved on this device. A live account-wide summary arrives with the backend’s list endpoints.</Banner>
      <OpenCircleSheet open={sheet} onClose={() => setSheet(false)} />
    </Screen>
  );
}
