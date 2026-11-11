'use client';
import Link from 'next/link';
import { useMemo } from 'react';
import { Icon } from '@/components/Icon';
import { CircleCard, DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Amount, EmptyState, LinkButton, SectionHead, Skeleton } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { useApi } from '@/lib/hooks';
import { sessionKey, useSession } from '@/lib/session';
import type { MyCircle } from '@/lib/types';
import { circleAttention, paymentOpen } from '@/lib/workflow';

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

/** Outstanding per currency, as reported by the server (summed only within one currency). */
function duesByCurrency(circles: MyCircle[]) {
  const out = new Map<string, number>();
  for (const c of circles) {
    const cy = c.current_cycle;
    if (cy && cy.my_outstanding && paymentOpen(c.payout_mode, cy)) out.set(c.currency, (out.get(c.currency) ?? 0) + cy.my_outstanding);
  }
  return [...out.entries()];
}

export default function HomePage() {
  const session = useSession();
  const circles = useApi(`circles:${sessionKey(session)}`, (s) => api.myCircles(session, s), { pollMs: 15000 });
  const first = session.user?.name.split(' ')[0] ?? '';

  return (
    <Screen title={`${greeting()}${first ? `, ${first}` : ''}`} subtitle="Here’s what needs you across your circles."
            actions={<LinkButton href="/app/circles/new" icon="plus" small>New circle</LinkButton>}>
      <DataBoundary state={circles} skeleton={<Skeleton count={3} />}>
        {(list) => <HomeBody circles={list} />}
      </DataBoundary>
    </Screen>
  );
}

function HomeBody({ circles }: { circles: MyCircle[] }) {
  const attention = useMemo(() => circles.flatMap(circleAttention), [circles]);
  const dues = duesByCurrency(circles);
  const organizing = circles.filter((c) => c.my_role === 'organizer').length;

  if (circles.length === 0) {
    return (
      <section className="card">
        <EmptyState icon="circles" title="No circles yet"
          action={<LinkButton href="/app/circles/new" icon="plus">Create your first circle</LinkButton>}>
          Organizing a circle? Set it up in a couple of minutes. Joining one? Ask the organizer to invite your email,
          and it will appear here automatically.
        </EmptyState>
      </section>
    );
  }

  return (
    <>
      <section className="card card--brand hero-card" aria-label="Summary">
        <div className="row row--between row--wrap">
          <div>
            <p className="muted small">You’re in {circles.length} circle{circles.length === 1 ? '' : 's'}{organizing ? ` · organizing ${organizing}` : ''}</p>
            <h2>{dues.length ? 'Contributions due' : 'You’re all paid up'}</h2>
          </div>
          <span className="glyph" style={{ background: 'rgba(255,255,255,.16)', color: '#fff' }}><Icon name="wallet" /></span>
        </div>
        <div className="row row--wrap" style={{ gap: 18 }}>
          {dues.length ? dues.map(([cur, minor]) => <Amount key={cur} minor={minor} currency={cur} size="xl" />)
            : <span className="muted">Nothing is due from you right now.</span>}
        </div>
      </section>

      <section className="stack" aria-label="Needs your attention">
        <SectionHead title="Needs your attention" />
        {attention.length === 0
          ? <p className="muted">Nothing waiting on you. Rounds move forward as members pay and the organizer approves.</p>
          : (
            <div className="attention">
              {attention.map((a) => (
                <Link key={a.id} href={a.href} className="attention__item">
                  <span className={`glyph glyph--${a.tone}`}><Icon name={a.icon} /></span>
                  <span className="grow"><strong>{a.title}</strong><span className="muted small">{a.body}</span></span>
                  <Icon name="chevronRight" />
                </Link>
              ))}
            </div>
          )}
      </section>

      <section className="stack" aria-label="Your circles">
        <SectionHead title="Your circles" action={<Link className="link" href="/app/circles">View all <Icon name="chevronRight" /></Link>} />
        <div className="circle-grid">
          {circles.slice(0, 4).map((c) => <CircleCard key={c.id} c={c} />)}
        </div>
      </section>
    </>
  );
}
