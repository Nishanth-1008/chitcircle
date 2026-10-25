'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useSession } from '@/lib/session';
import { Icon, type IconName } from './Icon';
import { DemoBanner, Skeleton, Wordmark } from './ui';

const NAV: { href: string; label: string; icon: IconName; match: string[] }[] = [
  { href: '/app/home', label: 'Home', icon: 'home', match: ['/app/home'] },
  { href: '/app/circles', label: 'Circles', icon: 'circles', match: ['/app/circles', '/app/settlements'] },
  { href: '/app/activity', label: 'Activity', icon: 'activity', match: ['/app/activity'] },
  { href: '/app/profile', label: 'Profile', icon: 'profile', match: ['/app/profile', '/app/help'] },
];

export function BottomNav() {
  const path = usePathname() ?? '';
  return (
    <nav className="bottomnav" aria-label="Main">
      {NAV.map((n) => {
        const active = n.match.some((m) => path === m || path.startsWith(`${m}/`));
        return (
          <Link key={n.href} href={n.href} aria-current={active ? 'page' : undefined}>
            <Icon name={n.icon} />
            <span>{n.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** Gate + frame for everything under /app. Identity comes from the session; role-specific UI is derived from server data. */
export function AppShell({ children }: { children: ReactNode }) {
  const { ready, actor, mode } = useSession();
  const router = useRouter();
  useEffect(() => { if (ready && !actor) router.replace('/welcome'); }, [ready, actor, router]);

  if (!ready || !actor) {
    return <div className="frame"><div className="app"><div className="screen"><Skeleton count={3} /></div></div></div>;
  }
  return (
    <div className="frame">
      <div className="app">
        {mode === 'demo' && <div className="banner--sticky"><DemoBanner /></div>}
        {children}
        <BottomNav />
      </div>
    </div>
  );
}

export function TopBar({ title, back, brand, right }: { title?: string; back?: string; brand?: boolean; right?: ReactNode }) {
  return (
    <header className="topbar">
      {back && <Link href={back} className="topbar__back" aria-label="Back"><Icon name="chevronLeft" /></Link>}
      <div className="topbar__title">{brand ? <Wordmark /> : <h1>{title}</h1>}</div>
      {right}
    </header>
  );
}

export function Screen({ title, back, brand, right, children }: {
  title?: string; back?: string; brand?: boolean; right?: ReactNode; children: ReactNode;
}) {
  return (
    <>
      <TopBar title={title} back={back} brand={brand} right={right} />
      <main className="screen">{children}</main>
    </>
  );
}
