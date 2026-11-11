/** Centralized route href helpers. Every dynamic segment is encoded so IDs with
 * special characters never break navigation. Use these instead of inline template
 * literals so all links stay consistent and correct. */

export function circleHref(circleId: string): string {
  return `/app/circles/${encodeURIComponent(circleId)}`;
}

export function circleCycleHref(circleId: string, cycleId: string): string {
  return `/app/circles/${encodeURIComponent(circleId)}/cycles/${encodeURIComponent(cycleId)}`;
}

export function settlementHref(settlementId: string): string {
  return `/app/settlements/${encodeURIComponent(settlementId)}`;
}

export function settlementReconciliationHref(settlementId: string): string {
  return `/app/settlements/${encodeURIComponent(settlementId)}/reconciliation`;
}

export function agentsHref(circleId: string): string {
  return `/app/circles/${encodeURIComponent(circleId)}/agents`;
}

export function newCircleHref(): string {
  return '/app/circles/new';
}

export function circlesHref(): string {
  return '/app/circles';
}

export function homeHref(): string {
  return '/app/home';
}

export function activityHref(circleId?: string | null): string {
  if (circleId) return `/app/activity?circle=${encodeURIComponent(circleId)}`;
  return '/app/activity';
}

export function profileHref(): string {
  return '/app/profile';
}

export function helpHref(): string {
  return '/app/help';
}

export function signInHref(): string {
  return '/sign-in';
}

export function registerHref(): string {
  return '/register';
}

export function welcomeHref(): string {
  return '/welcome';
}
