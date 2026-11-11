'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useAppConfig } from '@/lib/appConfig';
import { useSession } from '@/lib/session';
import { Icon, type IconName } from './Icon';
import { Avatar, Pill, Skeleton, Wordmark } from './ui';

const NAV: { href: string; label: string; icon: IconName; match: string[] }[] = [
  { href: '/app/home', label: 'Home', icon: 'home', match: ['/app/home'] },
  { href: '/app/circles', label: 'Circles', icon: 'circles', match: ['/app/circles', '/app/settlements'] },
  { href: '/app/activity', label: 'Activity', icon: 'activity', match: ['/app/activity'] },
  { href: '/app/profile', label: 'Profile', icon: 'profile', match: ['/app/profile', '/app/help'] },
];

function useActive() {
  const path = usePathname() ?? '';
  return (match: string[]) => match.some((m) => path === m || path.startsWith(`${m}/`));
}

function Sidebar() {
  const active = useActive();
  const { user } = useSession();
  const config = useAppConfig();
  return (
    <aside className="sidebar" aria-label="Main">
      <Link href="/app/home" className="sidebar__brand"><Wordmark /></Link>
      <nav className="sidebar__nav">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} aria-current={active(n.match) ? 'page' : undefined}>
            <Icon name={n.icon} /><span>{n.label}</span>
          </Link>
        ))}
      </nav>
      <Link href="/app/circles/new" className="btn btn--primary btn--sm btn--block"><Icon name="plus" />New circle</Link>
      <div className="sidebar__foot">
        {config?.sandbox_tools && <Pill tone="warning" icon="info">Sandbox</Pill>}
        <Link href="/app/profile" className="sidebar__user">
          <Avatar name={user?.name ?? '?'} small />
          <span className="grow"><b>{user?.name}</b><small>{user?.email}</small></span>
        </Link>
      </div>
    </aside>
  );
}

function BottomNav() {
  const active = useActive();
  return (
    <nav className="bottomnav" aria-label="Main">
      {NAV.map((n) => (
        <Link key={n.href} href={n.href} aria-current={active(n.match) ? 'page' : undefined}>
          <Icon name={n.icon} /><span>{n.label}</span>
        </Link>
      ))}
    </nav>
  );
}

/** Gate + frame for everything under /app. Signed-out visitors go to /welcome. */
export function AppShell({ children }: { children: ReactNode }) {
  const { ready, user } = useSession();
  const router = useRouter();
  useEffect(() => { if (ready && !user) router.replace('/welcome'); }, [ready, user, router]);

  if (!ready || !user) {
    return <div className="layout"><main className="main"><div className="page"><Skeleton count={3} /></div></main></div>;
  }
  return (
    <div className="layout">
      <Sidebar />
      <div className="main">{children}</div>
      <BottomNav />
    </div>
  );
}

export function Screen({ title, subtitle, back, actions, children, wide }: {
  title: ReactNode; subtitle?: ReactNode; back?: { href: string; label: string }; actions?: ReactNode;
  children: ReactNode; wide?: boolean;
}) {
  return (
    <>
      <header className="pagehead">
        <div className={`pagehead__inner${wide ? ' pagehead__inner--wide' : ''}`}>
          {back && (
            <Link href={back.href} className="pagehead__back"><Icon name="chevronLeft" />{back.label}</Link>
          )}
          <div className="pagehead__row">
            <div className="grow">
              <h1>{title}</h1>
              {subtitle && <div className="pagehead__sub">{subtitle}</div>}
            </div>
            {actions && <div className="pagehead__actions">{actions}</div>}
          </div>
        </div>
      </header>
      <main className={`page${wide ? ' page--wide' : ''}`}>{children}</main>
    </>
  );
}
