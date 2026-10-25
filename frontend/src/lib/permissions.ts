/**
 * UI-level role helpers. These decide what to SHOW, never what is allowed.
 * The backend remains the only authority: it re-checks organizer/approver identity on every command, and the
 * `X-Actor-*` headers are a development stub that must be replaced by real authentication.
 * Roles are derived from server data (circle.organizer_id / member ids), never from a client-side toggle.
 */
import type { CircleView, MemberView } from './types';

export interface Actor { id: string; role: string; displayName?: string }

export function isOrganizer(circle: Pick<CircleView, 'organizer_id'> | undefined, actor: Actor | null): boolean {
  return !!circle && !!actor && circle.organizer_id === actor.id;
}

export function memberFor(circle: Pick<CircleView, 'members'> | undefined, actor: Actor | null): MemberView | undefined {
  if (!circle || !actor) return undefined;
  return circle.members.find((m) => m.id === actor.id);
}

export type CircleRole = 'organizer' | 'member' | 'none';

export function roleIn(circle: CircleView | undefined, actor: Actor | null): CircleRole {
  if (isOrganizer(circle, actor)) return 'organizer';
  return memberFor(circle, actor) ? 'member' : 'none';
}

/** Security status is an organizer concern. Hiding it is a UI nicety; the API still returns it today. */
export const canViewMemberSecurity = (role: CircleRole) => role === 'organizer';
