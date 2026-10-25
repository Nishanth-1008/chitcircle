'use client';
import { useMemo, useState } from 'react';
import { CircleCard, DataBoundary } from '@/components/domain';
import { OpenCircleSheet } from '@/components/OpenCircleSheet';
import { Screen } from '@/components/shell';
import { Banner, Button, EmptyState, ErrorState, FilterTabs, Skeleton } from '@/components/ui';
import { myObligation } from '@/lib/derive';
import { resolveCurrency } from '@/lib/api/currency';
import { useOverviews, type OverviewItem } from '@/lib/overview';
import { useSaved } from '@/lib/saved';
import { useSession } from '@/lib/session';

type Tab = 'active' | 'payments' | 'completed';

export default function CirclesPage() {
  const ctx = useSession();
  const saved = useSaved(ctx.mode);
  const overview = useOverviews(ctx, saved.items);
  const [tab, setTab] = useState<Tab>('active');
  const [sheet, setSheet] = useState(false);
  const assumed = ctx.mode === 'live';

  const groups = useMemo(() => {
    const ok = (overview.data ?? []).filter((i) => i.circle);
    return {
      active: ok.filter((i) => !i.round || i.round.state !== 'FINALIZED'),
      payments: ok.filter((i) => (myObligation(i.round, ctx.actor)?.outstanding ?? 0) > 0),
      completed: ok.filter((i) => i.round?.state === 'FINALIZED'),
    } satisfies Record<Tab, OverviewItem[]>;
  }, [overview.data, ctx.actor]);
  const failed = (overview.data ?? []).filter((i) => !i.circle);

  const emptyCopy: Record<Tab, string> = {
    active: 'Circles with a round in progress appear here.',
    payments: 'You have nothing outstanding in the rounds saved on this device.',
    completed: 'Circles whose saved round is finalized appear here.',
  };

  return (
    <Screen title="My circles" right={<Button small icon="plus" onClick={() => setSheet(true)}>Open</Button>}>
      <FilterTabs label="Circle filter" value={tab} onChange={setTab} tabs={[
        { id: 'active', label: `Active${overview.data ? ` (${groups.active.length})` : ''}` },
        { id: 'payments', label: 'Payments' },
        { id: 'completed', label: 'Completed' },
      ]} />

      {saved.items.circles.length === 0 ? (
        <EmptyState icon="circles" title="No circles yet" action={<Button onClick={() => setSheet(true)}>Open a circle</Button>}>
          The backend can’t list your circles yet. Add one using its circle ID.
        </EmptyState>
      ) : (
        <DataBoundary state={overview} skeleton={<Skeleton count={3} />}>
          {() => (
            <>
              {groups[tab].length === 0 && failed.length === 0 && <EmptyState icon="circles" title="Nothing here">{emptyCopy[tab]}</EmptyState>}
              {groups[tab].map((it) => (
                <CircleCard key={it.circleId} item={it} actor={ctx.actor} currency={resolveCurrency().code} assumed={assumed} />
              ))}
              {tab === 'active' && failed.map((it) => (
                <section key={it.circleId} className="card stack">
                  <p className="num" style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>{it.circleId}</p>
                  <ErrorState error={it.circleError} compact />
                  <Button variant="ghost" small onClick={() => saved.forgetCircle(it.circleId)}>Remove from this device</Button>
                </section>
              ))}
            </>
          )}
        </DataBoundary>
      )}
      <Banner tone="neutral" icon="info">Showing circles saved on this device. “Completed” means the saved round is finalized.</Banner>
      <OpenCircleSheet open={sheet} onClose={() => setSheet(false)} />
    </Screen>
  );
}
