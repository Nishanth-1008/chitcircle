'use client';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { ActivityList, DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, Button, Card, EmptyState, LinkButton, Skeleton, Tabs } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { activityHref } from '@/lib/routes';
import { errorMessage } from '@/lib/api/errors';
import { useApi } from '@/lib/hooks';
import { FILTERS, matchesFilter, type FilterId } from '@/lib/ledger';
import { sessionKey, useSession } from '@/lib/session';
import type { LedgerEventView } from '@/lib/types';

export default function ActivityPage() {
  return <Suspense fallback={<div className="page"><Skeleton count={3} /></div>}><Activity /></Suspense>;
}

function Activity() {
  const session = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const key = sessionKey(session);
  const circles = useApi(`circles:${key}`, (s) => api.myCircles(session, s));
  const selected = params.get('circle') ?? circles.data?.[0]?.id ?? null;
  const circle = useApi(selected ? `circle:${key}:${selected}` : null, (s) => api.getCircle(session, selected!, s));
  const [filter, setFilter] = useState<FilterId>('all');
  const [extra, setExtra] = useState<LedgerEventView[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const first = useApi(selected ? `cfeed:${key}:${selected}` : null, (s) => api.circleLedger(session, selected!, { limit: 50 }, s), { pollMs: 20000 });

  useEffect(() => { setExtra([]); setCursor(null); }, [selected]);
  useEffect(() => { if (first.data && extra.length === 0) setCursor(first.data.next_cursor); }, [first.data, extra.length]);

  const loadMore = async () => {
    if (!cursor || !selected) return;
    setLoadingMore(true); setMoreError(null);
    try {
      const page = await api.circleLedger(session, selected, { cursor, limit: 50 });
      setExtra((e) => [...e, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) { setMoreError(errorMessage(e)); }
    finally { setLoadingMore(false); }
  };

  const nameOf = (id: string | null) => (id && circle.data?.members.find((m) => m.id === id)?.name) || (id ? 'Member' : 'Circle');

  return (
    <Screen title="Activity" subtitle="The shared ledger: every contribution, dividend, commission and payout, append-only.">
      <DataBoundary state={circles} skeleton={<Skeleton count={2} />}>
        {(list) => list.length === 0 ? (
          <Card><EmptyState icon="activity" title="No activity yet" action={<LinkButton href="/app/circles/new" icon="plus">Create a circle</LinkButton>}>
            Activity appears once you belong to a circle.</EmptyState></Card>
        ) : (
          <>
            <div className="row row--wrap">
              <label className="sr-only" htmlFor="circle-pick">Circle</label>
              <select id="circle-pick" style={{ maxWidth: 360 }} value={selected ?? ''}
                      onChange={(e) => router.replace(activityHref(e.target.value))}>
                {list.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <Tabs label="Filter activity" value={filter} onChange={setFilter} tabs={FILTERS} />
            <Card>
              <DataBoundary state={first} skeleton={<Skeleton kind="line" count={6} />}>
                {(page) => {
                  const events = [...page.items, ...extra].filter((e) => matchesFilter(e, filter));
                  return (
                    <>
                      <ActivityList events={events} nameOf={nameOf} showRound empty="Nothing matches this filter yet." />
                      {cursor && <Button variant="secondary" small onClick={() => void loadMore()} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load older entries'}</Button>}
                      {moreError && <Banner tone="danger">{moreError}</Banner>}
                    </>
                  );
                }}
              </DataBoundary>
            </Card>
            {circle.data?.my_role === 'member' && (
              <p className="muted small">You see your own entries plus circle-wide events (commission, payouts, disputes). Other members’ payments stay private.</p>
            )}
          </>
        )}
      </DataBoundary>
    </Screen>
  );
}
