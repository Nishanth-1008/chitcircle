/** Date helpers. Display only; due dates and states always come from the server. */
const dateFmt = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true });

export function formatDate(iso: string | null | undefined, short = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : (short ? shortFmt : dateFmt).format(d);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${shortFmt.format(d)}, ${timeFmt.format(d)}`;
}

export function formatClock(ts: number | null): string {
  return ts ? timeFmt.format(new Date(ts)) : '';
}

/** Whole days from `now` to the date (negative when past). */
export function daysUntil(iso: string, now: number = Date.now()): number {
  const d = Date.parse(iso);
  if (Number.isNaN(d)) return NaN;
  return Math.ceil((d - now) / 86_400_000);
}

export function dueLabel(iso: string, now: number = Date.now()): string {
  const n = daysUntil(iso, now);
  if (Number.isNaN(n)) return '—';
  if (n < 0) return `${-n} day${n === -1 ? '' : 's'} overdue`;
  if (n === 0) return 'Due today';
  return `${n} day${n === 1 ? '' : 's'} left`;
}

export function shortId(id: string, n = 8): string {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('');
}
