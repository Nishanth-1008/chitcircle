'use client';
import { useSearchParams } from 'next/navigation';
import { Suspense, useMemo, useState } from 'react';
import { ActivityRow, DataBoundary, useExpandable } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, EmptyState, FilterTabs, Skeleton } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { useApi } from '@/lib/hooks';
import { FILTERS, matchesFilter, sortLedger, type FilterId } from '@/lib/ledger';
import { useOverviews } from '@/lib/overview';
import { useSaved } from '@/lib/saved';
import { sessionKey, useSession } from '@/lib/session';

function ActivityInner() {
  const ctx = useSession();
  const params = useSearchParams();
  const saved = useSaved(ctx.mode);
  const overview = useOverviews(ctx, saved.items);
  const [filter, setFilter] = useState<FilterId>('all');
  const [chosen, setChosen] = useState<string | null>(null);
  const { open, toggle } = useExpandable();

  const rounds = useMemo(() => (overview.data ?? []).filter((i) => i.circle && i.round), [overview.data]);
  const selectedId = chosen ?? params.get('round') ?? rounds[0]?.round?.id ?? null;
  const selected = rounds.find((r) => r.round!.id === selectedId);

  const ledger = useApi(selectedId ? `ledger:${sessionKey(ctx)}:${selectedId}` : null, (s) => api.getLedger(ctx, selectedId!, s));

  return (
    <Screen title="Activity">
      <Banner tone="neutral" icon="info">Activity is shown one round at a time. A combined feed needs a backend update.</Banner>

      {saved.items.rounds.length === 0 ? (
        <EmptyState icon="activity" title="No rounds to show">Open a circle, then a round, and its ledger will appear here.</EmptyState>
      ) : (
        <>
          <DataBoundary state={overview} skeleton={<Skeleton kind="line" count={2} />}>
            {() => (
              rounds.length > 0 ? (
                <div className="tabs" role="tablist" aria-label="Round">
                  {rounds.map((r) => (
                    <button key={r.round!.id} type="button" role="tab" className="tab" aria-selected={r.round!.id === selectedId}
                            onClick={() => { setChosen(r.round!.id); }}>
                      {r.circle!.name} · R{r.round!.number}
                    </button>
                  ))}
                </div>
              ) : <EmptyState icon="activity" title="Couldn’t load your rounds">Check the Circles tab for details.</EmptyState>
            )}
          </DataBoundary>

          {selectedId && (
            <>
              <FilterTabs label="Activity filter" tabs={FILTERS} value={filter} onChange={setFilter} />
              <DataBoundary state={ledger} skeleton={<Skeleton count={4} />}>
                {(events) => {
                  const rows = sortLedger(events).filter((e) => matchesFilter(e, filter));
                  if (rows.length === 0) {
                    return <EmptyState icon="activity" title="Nothing matches">{events.length === 0 ? 'This round has no ledger entries yet.' : 'Try a different filter.'}</EmptyState>;
                  }
                  return (
                    <section className="card" aria-label="Ledger">
                      <ul className="activity">
                        {rows.map((e) => (
                          <ActivityRow key={e.id} event={e} memberById={(id) => selected?.circle?.members.find((m) => m.id === id)}
                                       demo={ctx.mode === 'demo'} expanded={open === e.id} onToggle={() => toggle(e.id)} />
                        ))}
                      </ul>
                    </section>
                  );
                }}
              </DataBoundary>
              <p className="muted" style={{ fontSize: 12 }}>
                “Contribution due” rows are scheduled obligations, not payments. Only provider-confirmed rows count as money received.
              </p>
            </>
          )}
        </>
      )}
    </Screen>
  );
}

export default function ActivityPage() {
  return <Suspense fallback={<Screen title="Activity"><Skeleton count={3} /></Screen>}><ActivityInner /></Suspense>;
}
