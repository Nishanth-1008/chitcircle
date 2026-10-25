'use client';
import Link from 'next/link';
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { describeError } from '@/lib/api/errors';
import { ApiError } from '@/lib/api/errors';
import { formatClock } from '@/lib/format';
import { safeFormatMinor } from '@/lib/money';
import type { Tone } from '@/lib/status';
import { Icon, type IconName } from './Icon';

export function Wordmark({ large = false }: { large?: boolean }) {
  return (
    <span className={`wordmark${large ? ' wordmark--lg' : ''}`} aria-label="ChitCircle">
      <span>Chit</span><b>Circle</b><i aria-hidden="true" />
    </span>
  );
}

type BtnVariant = 'primary' | 'secondary' | 'soft' | 'ghost';
interface BtnCommon { variant?: BtnVariant; small?: boolean; block?: boolean; icon?: IconName; children: ReactNode }

export function Button({ variant = 'primary', small, block, icon, children, className = '', ...rest }:
  BtnCommon & ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = `btn btn--${variant}${small ? ' btn--sm' : ''}${block ? ' btn--block' : ''} ${className}`;
  return <button type="button" className={cls} {...rest}>{icon && <Icon name={icon} />}{children}</button>;
}

export function LinkButton({ href, variant = 'primary', small, block, icon, children }: BtnCommon & { href: string }) {
  const cls = `btn btn--${variant}${small ? ' btn--sm' : ''}${block ? ' btn--block' : ''}`;
  return <Link href={href} className={cls}>{icon && <Icon name={icon} />}{children}</Link>;
}

export function StatusPill({ tone = 'neutral', icon, children }: { tone?: Tone; icon?: IconName; children: ReactNode }) {
  return <span className={`pill pill--${tone}`}>{icon && <Icon name={icon} />}{children}</span>;
}

export function DemoPill() { return <span className="pill pill--demo">Demo</span>; }

export type AmountTone = 'income' | 'expense' | 'warning' | 'muted' | 'default';

export function Amount({ minor, currency, assumed, tone = 'default', size = 'sm', signed, precise }: {
  minor: number | null | undefined; currency: string; assumed?: boolean; tone?: AmountTone;
  size?: 'sm' | 'md' | 'lg'; signed?: boolean; precise?: boolean;
}) {
  const text = safeFormatMinor(minor, currency, { signed, precise });
  const cls = `amount num amount--${size}${tone !== 'default' ? ` amount--${tone}` : ''}`;
  return (
    <span className={cls}>
      {text}
      {assumed && <span className="assumed" title={`The server did not send a currency for this value; showing ${currency} from app configuration.`}>{currency} assumed</span>}
    </span>
  );
}

export function ProgressBar({ value, max, label, right }: { value: number; max: number; label?: string; right?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0;
  return (
    <div>
      {(label || right) && <div className="progress-label"><span>{label}</span><span>{right}</span></div>}
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label ?? 'Progress'}>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function FilterTabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: { id: T; label: string }[]; value: T; onChange: (id: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} role="tab" type="button" className="tab" aria-selected={t.id === value} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Banner({ tone = 'info', icon = 'info', children }: { tone?: 'demo' | 'info' | 'warning' | 'danger' | 'neutral'; icon?: IconName; children: ReactNode }) {
  return <div className={`banner banner--${tone}`} role={tone === 'danger' ? 'alert' : 'note'}><Icon name={icon} /><div>{children}</div></div>;
}

export function DemoBanner() {
  return <Banner tone="demo" icon="alert">Demo mode — no real money moves. All names, amounts and IDs are fictional.</Banner>;
}

export function SectionHead({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="section-head"><h2>{title}</h2>{action}</div>;
}

export function Avatar({ name, small }: { name: string; small?: boolean }) {
  const t = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('');
  return <span className={`avatar${small ? ' avatar--sm' : ''}`} aria-hidden="true">{t || '?'}</span>;
}

export function EmptyState({ icon = 'circles', title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state__icon"><Icon name={icon} /></div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const { title, message } = describeError(error);
  const kind = error instanceof ApiError ? error.kind : 'server';
  const icon: IconName = kind === 'forbidden' || kind === 'unauthorized' ? 'lock' : kind === 'network' ? 'refresh' : kind === 'not_found' ? 'search' : 'alert';
  const retryable = kind === 'network' || kind === 'server' || kind === 'unavailable';
  return (
    <div className="state" role="alert" style={compact ? { padding: '16px 8px' } : undefined}>
      <div className={`state__icon ${kind === 'forbidden' || kind === 'unauthorized' ? 'state__icon--warning' : 'state__icon--danger'}`}><Icon name={icon} /></div>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry && retryable && <Button variant="secondary" small icon="refresh" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Skeleton({ kind = 'card', count = 1 }: { kind?: 'card' | 'line'; count?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: count }, (_, i) => <div key={i} className={`skeleton skeleton--${kind}`} />)}
    </div>
  );
}

/** Shown when a refresh failed but older data is still on screen. */
export function StaleNotice({ updatedAt, onRetry }: { updatedAt: number | null; onRetry: () => void }) {
  return (
    <div className="banner banner--warning" role="status">
      <Icon name="clock" />
      <div className="stale">
        <span>Couldn’t refresh. Showing data from {formatClock(updatedAt) || 'earlier'}.</span>
        <button type="button" className="link" onClick={onRetry}>Retry</button>
      </div>
    </div>
  );
}

export function BottomSheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('input, button, select')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sheet-scrim" onClick={onClose}>
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet__grab" />
        <div className="stack stack--lg">
          <h2>{title}</h2>
          {children}
        </div>
      </div>
    </div>
  );
}
