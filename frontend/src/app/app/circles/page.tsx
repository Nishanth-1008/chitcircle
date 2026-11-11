'use client';
import { useState } from 'react';
import { CircleCard, DataBoundary } from '@/components/domain';
import { Screen } from '@/components/shell';
import { EmptyState, LinkButton, Skeleton, Tabs } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { useApi } from '@/lib/hooks';
import { sessionKey, useSession } from '@/lib/session';
import type { MyCircle } from '@/lib/types';

type Filter = 'all' | 'organizing' | 'member' | 'completed';

const matches = (c: MyCircle, f: Filter) => {
  const done = c.won_count >= c.member_count && c.current_cycle?.state === 'FINALIZED';
  if (f === 'completed') return done;
  if (done) return false;
  if (f === 'organizing') return c.my_role === 'organizer';
  if (f === 'member') return c.my_role === 'member';
  return true;
};

export default function CirclesPage() {
  const session = useSession();
  const circles = useApi(`circles:${sessionKey(session)}`, (s) => api.myCircles(session, s));
  const [filter, setFilter] = useState<Filter>('all');

  return (
    <Screen title="Circles" subtitle="Every circle you organize or hold a seat in."
            actions={<LinkButton href="/app/circles/new" icon="plus" small>New circle</LinkButton>}>
      <DataBoundary state={circles} skeleton={<Skeleton count={3} />}>
        {(list) => {
          const shown = list.filter((c) => matches(c, filter));
          return (
            <>
              <Tabs label="Filter circles" value={filter} onChange={setFilter} tabs={[
                { id: 'all', label: 'Active' },
                { id: 'organizing', label: 'Organizing', count: list.filter((c) => matches(c, 'organizing')).length },
                { id: 'member', label: 'Member', count: list.filter((c) => matches(c, 'member')).length },
                { id: 'completed', label: 'Completed' },
              ]} />
              {shown.length === 0 ? (
                <section className="card">
                  <EmptyState icon="circles" title={list.length ? 'Nothing here' : 'No circles yet'}
                    action={list.length ? undefined : <LinkButton href="/app/circles/new" icon="plus">Create a circle</LinkButton>}>
                    {list.length ? 'No circles match this filter.' : 'Create a circle, or ask an organizer to invite your email address.'}
                  </EmptyState>
                </section>
              ) : (
                <div className="circle-grid">{shown.map((c) => <CircleCard key={c.id} c={c} />)}</div>
              )}
            </>
          );
        }}
      </DataBoundary>
    </Screen>
  );
}
