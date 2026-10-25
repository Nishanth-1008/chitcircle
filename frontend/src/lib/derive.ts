import type { Actor } from './permissions';
import type { CircleView, CycleView, ObligationView } from './types';

/** Reads server-provided obligation fields; performs no financial calculation. */
export const myObligation = (cycle: CycleView | undefined, actor: Actor | null): ObligationView | undefined =>
  actor ? cycle?.obligations?.find((o) => o.member_id === actor.id) : undefined;

/** Count of members the server reports as having nothing outstanding. */
export const settledCount = (cycle: CycleView | undefined): number =>
  cycle?.obligations?.filter((o) => o.outstanding === 0).length ?? 0;

export const memberName = (circle: CircleView | undefined, memberId: string | null | undefined): string =>
  (memberId && circle?.members.find((m) => m.id === memberId)?.name) || (memberId ? `Member ${memberId.slice(0, 6)}` : '—');
