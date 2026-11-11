'use client';
import Link from 'next/link';
import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { ApiError, describeError } from '@/lib/api/errors';
import { formatClock, initials } from '@/lib/format';
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

type BtnVariant = 'primary' | 'secondary' | 'soft' | 'ghost' | 'danger';
interface BtnCommon { variant?: BtnVariant; small?: boolean; block?: boolean; icon?: IconName; children: ReactNode }

export function Button({ variant = 'primary', small, block, icon, children, className = '', ...rest }:
  BtnCommon & ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = `btn btn--${variant}${small ? ' btn--sm' : ''}${block ? ' btn--block' : ''} ${className}`;
  return <button type="button" className={cls} {...rest}>{icon && <Icon name={icon} />}{children}</button>;
}

export function LinkButton({ href, variant = 'primary', small, block, icon, children, external }:
  BtnCommon & { href: string; external?: boolean }) {
  const cls = `btn btn--${variant}${small ? ' btn--sm' : ''}${block ? ' btn--block' : ''}`;
  if (external) {
    return <a href={href} className={cls} target="_blank" rel="noreferrer">{icon && <Icon name={icon} />}{children}</a>;
  }
  return <Link href={href} className={cls}>{icon && <Icon name={icon} />}{children}</Link>;
}

export function Pill({ tone = 'neutral', icon, children }: { tone?: Tone; icon?: IconName; children: ReactNode }) {
  return <span className={`pill pill--${tone}`}>{icon && <Icon name={icon} />}{children}</span>;
}

export type AmountTone = 'income' | 'expense' | 'warning' | 'muted' | 'default';

export function Amount({ minor, currency, tone = 'default', size = 'sm', signed, precise }: {
  minor: number | null | undefined; currency: string; tone?: AmountTone;
  size?: 'sm' | 'md' | 'lg' | 'xl'; signed?: boolean; precise?: boolean;
}) {
  const cls = `amount num amount--${size}${tone !== 'default' ? ` amount--${tone}` : ''}`;
  return <span className={cls}>{safeFormatMinor(minor, currency, { signed, precise })}</span>;
}

export function ProgressBar({ value, max, label, right, tone = 'brand' }: {
  value: number; max: number; label?: string; right?: string; tone?: 'brand' | 'income' | 'warning';
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0;
  return (
    <div className="progress-wrap">
      {(label || right) && <div className="progress-label"><span>{label}</span><span>{right}</span></div>}
      <div className={`progress progress--${tone}`} role="progressbar" aria-valuemin={0} aria-valuemax={max}
           aria-valuenow={value} aria-label={label ?? 'Progress'}>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (id: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} role="tab" type="button" className="tab" aria-selected={t.id === value} onClick={() => onChange(t.id)}>
          {t.label}{t.count !== undefined && t.count > 0 && <span className="tab__count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Banner({ tone = 'info', icon, title, children, action }: {
  tone?: 'info' | 'warning' | 'danger' | 'neutral' | 'success'; icon?: IconName; title?: string; children?: ReactNode; action?: ReactNode;
}) {
  const ic: IconName = icon ?? (tone === 'danger' || tone === 'warning' ? 'alert' : tone === 'success' ? 'checkCircle' : 'info');
  return (
    <div className={`banner banner--${tone}`} role={tone === 'danger' ? 'alert' : 'note'}>
      <Icon name={ic} />
      <div className="grow">
        {title && <strong className="banner__title">{title}</strong>}
        {children && <div>{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function Card({ title, subtitle, action, children, className = '', tone }: {
  title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children?: ReactNode; className?: string;
  tone?: 'soft' | 'brand' | 'warning' | 'danger';
}) {
  return (
    <section className={`card${tone ? ` card--${tone}` : ''} ${className}`}>
      {(title || action) && (
        <header className="card__head">
          <div className="grow">
            {title && <h3>{title}</h3>}
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function SectionHead({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="section-head"><h2>{title}</h2>{action}</div>;
}

export function Avatar({ name, small, you }: { name: string; small?: boolean; you?: boolean }) {
  return <span className={`avatar${small ? ' avatar--sm' : ''}${you ? ' avatar--you' : ''}`} aria-hidden="true">{initials(name) || '?'}</span>;
}

export function Stat({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className="stat__value">{children}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </div>
  );
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

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { title, message } = describeError(error);
  const kind = error instanceof ApiError ? error.kind : 'server';
  const icon: IconName = kind === 'forbidden' || kind === 'unauthorized' ? 'lock' : kind === 'network' ? 'refresh' : kind === 'not_found' ? 'search' : 'alert';
  return (
    <div className="state" role="alert">
      <div className={`state__icon ${kind === 'forbidden' ? 'state__icon--warning' : 'state__icon--danger'}`}><Icon name={icon} /></div>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry && kind !== 'forbidden' && kind !== 'not_found' && <Button variant="secondary" small icon="refresh" onClick={onRetry}>Try again</Button>}
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

export function StaleNotice({ updatedAt, onRetry }: { updatedAt: number | null; onRetry: () => void }) {
  return (
    <div className="banner banner--warning" role="status">
      <Icon name="clock" />
      <div className="grow">Couldn’t refresh. Showing data from {formatClock(updatedAt) || 'earlier'}.</div>
      <button type="button" className="link" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function InlineError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return <p className="field__error" role="alert">{message}</p>;
}

export function Field({ label, help, error, children }: { label: string; help?: ReactNode; error?: string | null; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {error ? <span className="field__error" role="alert">{error}</span> : help ? <span className="field__help">{help}</span> : null}
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('input, select, textarea, button:not(.modal__close)')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="modal__head">
          <h2>{title}</h2>
          <button type="button" className="modal__close" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function KeyValue({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v], i) => (<div key={i}><dt>{k}</dt><dd>{v}</dd></div>))}
    </dl>
  );
}
