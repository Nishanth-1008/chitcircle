import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const nav = vi.hoisted(() => ({
  replace: vi.fn(), push: vi.fn(), params: {} as Record<string, string>, path: '/app/home', search: new URLSearchParams(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: nav.replace, push: nav.push, back: vi.fn() }),
  usePathname: () => nav.path,
  useParams: () => nav.params,
  useSearchParams: () => nav.search,
  redirect: vi.fn(),
}));

import { AppShell } from '@/components/shell';
import { SessionProvider } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';
import HomePage from '@/app/app/home/page';
import CirclesPage from '@/app/app/circles/page';
import CircleDetailPage from '@/app/app/circles/[circleId]/page';
import RoundPage from '@/app/app/circles/[circleId]/cycles/[cycleId]/page';
import ActivityPage from '@/app/app/activity/page';
import SettlementPage from '@/app/app/settlements/[settlementId]/page';
import ReconciliationPage from '@/app/app/settlements/[settlementId]/reconciliation/page';
import ProfilePage from '@/app/app/profile/page';
import HelpPage from '@/app/app/help/page';

const wrap = (ui: ReactNode) => render(<ThemeProvider><SessionProvider><AppShell>{ui}</AppShell></SessionProvider></ThemeProvider>);
const signIn = (actorId: string, role: string) =>
  window.localStorage.setItem('chitcircle.session.v1', JSON.stringify({ actor: { id: actorId, role, displayName: actorId } }));

beforeEach(() => { nav.replace.mockReset(); nav.push.mockReset(); nav.params = {}; nav.search = new URLSearchParams(); });

describe('app shell', () => {
  it('sends signed-out visitors to /welcome', async () => {
    wrap(<div>secret</div>);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/welcome'));
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });
  it('shows the four-tab bottom navigation', async () => {
    signIn('alex', 'member'); nav.path = '/app/circles';
    wrap(<div>content</div>);
    const nav4 = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav4).getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Circles', 'Activity', 'Profile']);
    expect(within(nav4).getByText('Circles').closest('a')).toHaveAttribute('aria-current', 'page');
  });
});

describe('Home', () => {
  it('shows empty state when nothing is saved', async () => {
    signIn('alex', 'member'); nav.path = '/app/home';
    wrap(<HomePage />);
    expect(await screen.findByText('No circles yet')).toBeInTheDocument();
  });
  it('opens the "Open a circle" sheet', async () => {
    signIn('alex', 'member'); wrap(<HomePage />);
    const buttons = await screen.findAllByRole('button', { name: /open a circle/i });
    await userEvent.click(buttons[0]);
    expect(await screen.findByRole('dialog', { name: 'Open a circle' })).toBeInTheDocument();
  });
});

describe('Circles list', () => {
  it('shows empty state when nothing is saved', async () => {
    signIn('alex', 'member'); nav.path = '/app/circles';
    wrap(<CirclesPage />);
    expect(await screen.findByText('No circles yet')).toBeInTheDocument();
  });
});

describe('Profile + Help', () => {
  it('persists the theme choice', async () => {
    signIn('alex', 'member'); wrap(<ProfilePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dark' }));
    expect(window.localStorage.getItem('chitcircle.theme')).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  });
  it('signing out clears the session and returns to /welcome', async () => {
    signIn('alex', 'member'); wrap(<ProfilePage />);
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }));
    expect(window.localStorage.getItem('chitcircle.session.v1')).toBeNull();
    expect(nav.replace).toHaveBeenCalledWith('/welcome');
  });
  it('help is honest about what is not connected', async () => {
    signIn('alex', 'member'); wrap(<HelpPage />);
    expect(await screen.findByText('Pay a contribution online')).toBeInTheDocument();
    expect(screen.getAllByText('Not connected').length).toBeGreaterThan(5);
    expect(screen.getByText(/payout provider integration is a stub/i)).toBeInTheDocument();
  });
});
