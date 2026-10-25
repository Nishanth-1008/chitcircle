'use client';
import { api } from './api/endpoints';
import type { ApiContext } from './api/client';
import { sessionKey } from './session';
import { useApi } from './hooks';
import { latestRoundFor, type SavedItems } from './saved';
import type { CircleView, CycleView } from './types';

export interface OverviewItem {
  circleId: string;
  circle?: CircleView;
  round?: CycleView;
  circleError?: Error;
  roundError?: Error;
}

/**
 * Loads every saved circle (and its most recent saved round) from the authoritative GET endpoints.
 * Failures are kept per item so one forbidden/missing circle never blanks the whole list.
 */
export function useOverviews(ctx: ApiContext, saved: SavedItems) {
  const sig = saved.circles.map((c) => `${c.id}>${latestRoundFor(saved, c.id)?.id ?? ''}`).join('|');
  return useApi<OverviewItem[]>(`overview:${sessionKey(ctx)}:${sig}`, async (signal) => {
    return Promise.all(saved.circles.map(async (c): Promise<OverviewItem> => {
      const roundRef = latestRoundFor(saved, c.id);
      const [circle, round] = await Promise.allSettled([
        api.getCircle(ctx, c.id, signal),
        roundRef ? api.getCycle(ctx, roundRef.id, signal) : Promise.resolve(undefined),
      ]);
      return {
        circleId: c.id,
        circle: circle.status === 'fulfilled' ? circle.value : undefined,
        circleError: circle.status === 'rejected' ? (circle.reason as Error) : undefined,
        round: round.status === 'fulfilled' ? round.value : undefined,
        roundError: round.status === 'rejected' ? (round.reason as Error) : undefined,
      };
    }));
  });
}
