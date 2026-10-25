import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEMO_CIRCLE_IDS, DEMO_CYCLE_IDS, DEMO_SETTLEMENT_ID } from '@/lib/api/demo';
import { SessionProvider } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';

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
const signInDemo = () =>
  window.localStorage.setItem('chitcircle.session.v1', JSON.stringify({ mode: 'demo', actor: { id: 'demo-alex', role: 'member', displayName: 'Alex' } }));

beforeEach(() => { nav.replace.mockReset(); nav.push.mockReset(); nav.params = {}; nav.search = new URLSearchParams(); });

describe('app shell', () => {
  it('sends signed-out visitors to /welcome', async () => {
    wrap(<div>secret</div>);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/welcome'));
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });
  it('shows the demo banner and the four-tab bottom navigation with an active state', async () => {
    signInDemo(); nav.path = '/app/circles';
    wrap(<div>content</div>);
    expect(await screen.findByText(/no real money moves/i)).toBeInTheDocument();
    const nav4 = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav4).getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Circles', 'Activity', 'Profile']);
    expect(within(nav4).getByText('Circles').closest('a')).toHaveAttribute('aria-current', 'page');
  });
});

describe('Home (demo)', () => {
  it('shows what is due, from server data, and does not claim online payment works', async () => {
    signInDemo(); nav.path = '/app/home';
    wrap(<HomePage />);
    expect(await screen.findByText(/Good (morning|afternoon|evening), Alex/)).toBeInTheDocument();
    const due = await screen.findByLabelText('Next installment due');
    expect(within(due).getByText('₹10,000')).toBeInTheDocument();
    expect(within(due).getByText(/payment isn’t connected yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pay now/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/escrow|RBI|insured|audited/i)).not.toBeInTheDocument();
  });
  it('shows the empty state when nothing is saved in live-like mode', async () => {
    signInDemo(); window.localStorage.setItem('chitcircle.saved.v1.demo', JSON.stringify({ circles: [], rounds: [] }));
    wrap(<HomePage />);
    expect(await screen.findByText('No circles yet')).toBeInTheDocument();
  });
  it('opens the "Open a circle" sheet', async () => {
    signInDemo(); wrap(<HomePage />);
    await userEvent.click(await screen.findByRole('button', { name: /open a circle/i }));
    expect(await screen.findByRole('dialog', { name: 'Open a circle' })).toBeInTheDocument();
  });
});

describe('Circles list (demo)', () => {
  it('lists saved circles with status and filters', async () => {
    signInDemo(); nav.path = '/app/circles';
    wrap(<CirclesPage />);
    expect(await screen.findByText('Weekend Family Chit #4')).toBeInTheDocument();
    expect(screen.getByText('Tech Colleagues Circle')).toBeInTheDocument();
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Payments' }));
    expect(screen.queryByText('Weekend Family Chit #4')).not.toBeInTheDocument();
    expect(screen.getByText('Tech Colleagues Circle')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Completed' }));
    expect(await screen.findByText('Nothing here')).toBeInTheDocument();
  });
  it('shows a per-item permission/not-found error without blanking the list', async () => {
    signInDemo();
    window.localStorage.setItem('chitcircle.saved.v1.demo', JSON.stringify({ circles: [{ id: DEMO_CIRCLE_IDS.tech, savedAt: 2 }, { id: 'missing', savedAt: 1 }], rounds: [] }));
    wrap(<CirclesPage />);
    expect(await screen.findByText('Tech Colleagues Circle')).toBeInTheDocument();
    expect(await screen.findByText('Not found')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove from this device/i })).toBeInTheDocument();
  });
});

describe('Circle details', () => {
  it('shows members, role badge, and hides security status from non-organizers', async () => {
    signInDemo(); nav.params = { circleId: DEMO_CIRCLE_IDS.tech };
    wrap(<CircleDetailPage />);
    expect(await screen.findByText('You’re a member')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Members' }));
    expect(await screen.findByText('Neha Gupta')).toBeInTheDocument();
    expect(screen.queryByText(/security (verified|pending)/i)).not.toBeInTheDocument();
  });
  it('organizers see security status', async () => {
    signInDemo(); nav.params = { circleId: DEMO_CIRCLE_IDS.weekend };
    wrap(<CircleDetailPage />);
    expect(await screen.findByText('You organize this circle')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Members' }));
    expect((await screen.findAllByText(/security verified/i)).length).toBeGreaterThan(0);
  });
  it('shows a not-found error state for an unknown circle', async () => {
    signInDemo(); nav.params = { circleId: 'nope' };
    wrap(<CircleDetailPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Not found');
  });
});

describe('Round (cycle) workspace', () => {
  it('renders status, stepper, own contribution, recipient, settlement link and activity', async () => {
    signInDemo(); nav.params = { circleId: DEMO_CIRCLE_IDS.weekend, cycleId: DEMO_CYCLE_IDS.weekend };
    wrap(<RoundPage />);
    expect(await screen.findByLabelText('Round status')).toHaveTextContent('Awaiting approval');
    expect(screen.getByRole('list', { name: 'Round progress' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Recipient')).toHaveTextContent('Lakshmi Devi');
    expect(await screen.findByRole('link', { name: 'Review settlement' })).toHaveAttribute('href', `/app/settlements/${DEMO_SETTLEMENT_ID}`);
    expect(await screen.findByLabelText('Auction bids')).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been paid out/i)).toBeInTheDocument();
  });
  it('shows an outstanding contribution and never a pay button', async () => {
    signInDemo(); nav.params = { circleId: DEMO_CIRCLE_IDS.tech, cycleId: DEMO_CYCLE_IDS.tech };
    wrap(<RoundPage />);
    const mine = await screen.findByLabelText('Your contribution');
    expect(within(mine).getByText('Outstanding', { selector: '.pill' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pay/i })).not.toBeInTheDocument();
  });
  it('rejects a round opened under the wrong circle', async () => {
    signInDemo(); nav.params = { circleId: DEMO_CIRCLE_IDS.tech, cycleId: DEMO_CYCLE_IDS.weekend };
    wrap(<RoundPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/different circle/i);
  });
});

describe('Activity', () => {
  it('lists ledger rows, distinguishes due from paid, filters, and expands details', async () => {
    signInDemo(); nav.search = new URLSearchParams({ round: DEMO_CYCLE_IDS.tech });
    wrap(<ActivityPage />);
    const ledger = await screen.findByLabelText('Ledger');
    expect(within(ledger).getAllByText('Contribution due').length).toBe(12);
    expect(within(ledger).getAllByText('Contribution received').length).toBe(9);
    expect((await screen.findAllByText('Demo')).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('tab', { name: 'Incoming' }));
    expect(screen.queryByText('Contribution due')).not.toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: /Contribution received/ })[0]);
    expect(await screen.findByText('Provider ref')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Journal postings' })).toBeInTheDocument();
  });
});

describe('Settlement + reconciliation (read-only)', () => {
  it('renders the server breakdown and never offers write actions', async () => {
    signInDemo(); nav.params = { settlementId: DEMO_SETTLEMENT_ID };
    wrap(<SettlementPage />);
    const b = await screen.findByLabelText('Settlement breakdown');
    expect(within(b).getByText('Gross chit value').closest('.breakdown__row')).toHaveTextContent('₹50,000.00');
    expect(within(b).getByText('Winner payout').closest('.breakdown__row')).toHaveTextContent('₹46,000.00');
    expect(within(b).getByText('Organizer commission').closest('.breakdown__row')).toHaveTextContent('₹2,500.00');
    expect(await screen.findByLabelText('Your net contribution')).toHaveTextContent('₹4,850.00');
    expect(await screen.findByLabelText('Settlement status')).toHaveTextContent('Awaiting approval');
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    for (const name of [/approve/i, /reject/i, /request payout/i, /finalize/i]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });
  it('shows reconciliation required with discrepancies in plain language', async () => {
    signInDemo(); nav.params = { settlementId: DEMO_SETTLEMENT_ID };
    wrap(<ReconciliationPage />);
    expect(await screen.findByText('Reconciliation required')).toBeInTheDocument();
    expect((await screen.findAllByText('Paid less than the amount due')).length).toBe(2);
    expect(screen.getByText(/No provider-confirmed payout yet/i)).toBeInTheDocument();
  });
  it('shows not-found for an unknown settlement', async () => {
    signInDemo(); nav.params = { settlementId: 'zzz' };
    wrap(<SettlementPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Not found');
  });
});

describe('Profile + Help', () => {
  it('persists the theme choice', async () => {
    signInDemo(); wrap(<ProfilePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dark' }));
    expect(window.localStorage.getItem('chitcircle.theme')).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  });
  it('signing out clears the session and returns to /welcome', async () => {
    signInDemo(); wrap(<ProfilePage />);
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }));
    expect(window.localStorage.getItem('chitcircle.session.v1')).toBeNull();
    expect(nav.replace).toHaveBeenCalledWith('/welcome');
  });
  it('help is honest about what is not connected', async () => {
    signInDemo(); wrap(<HelpPage />);
    expect(await screen.findByText('Pay a contribution online')).toBeInTheDocument();
    expect(screen.getAllByText('Not connected').length).toBeGreaterThan(5);
    expect(screen.getByText(/payout provider integration is a stub/i)).toBeInTheDocument();
  });
});
