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
import { ToastProvider } from '@/lib/toast';
import HomePage from '@/app/app/home/page';
import CirclesPage from '@/app/app/circles/page';
import CirclePage from '@/app/app/circles/[circleId]/page';
import RoundPage from '@/app/app/circles/[circleId]/cycles/[cycleId]/page';
import SettlementPage from '@/app/app/settlements/[settlementId]/page';
import ProfilePage from '@/app/app/profile/page';
import SignIn from '@/app/sign-in/page';
import type { CircleView, CycleView, MyCircle, SettlementView } from '@/lib/types';

const ORG = { id: 'org', email: 'org@example.com', name: 'Asha Organizer', role: 'member', payout_email: null, payout_email_verified: false };
const MEM = { ...ORG, id: 'u-ravi', email: 'ravi@example.com', name: 'Ravi Kumar' };

const ruleset = {
  currency: 'INR', total_chit_value: 400_000, member_count: 4, payout_mode: 'SEALED_BID_AUCTION',
  commission: { base: 'PERCENT_OF_CHIT_VALUE', rate: '0.05', fixed_amount: null, rounding: 'HALF_UP' },
  dividend: { allocation: 'ALL_MEMBERS' }, grace_period_days: 3, required_approvals: 1, require_security: false,
  auction: { max_discount_rate: '0.3', tie_break: 'EARLIEST_BID', no_bid_fallback: 'HOLD', min_discount: 0, increment: 0 },
  rounding: { contribution_remainder: 'REJECT', remainder_destination: 'ORGANIZER' },
  require_full_collection_before_payout: true, one_win_per_member: true, jurisdiction_profile: 'IN-SANDBOX',
  effective_date: '2026-11-01', allow_agreed_discount: false,
};
const members = ['Asha Organizer', 'Ravi Kumar', 'Meena', 'Joe'].map((name, i) => ({
  id: `m${i + 1}`, name, position: i + 1, has_won: false, security_status: 'NONE', user_id: i === 0 ? 'org' : i === 1 ? 'u-ravi' : null, linked: i < 2,
}));
const circleFor = (me: typeof ORG): CircleView => ({
  id: 'c1', name: 'Family chit', organizer_id: 'org', created_at: null, my_role: me.id === 'org' ? 'organizer' : 'member',
  my_member_id: me.id === 'org' ? 'm1' : 'm2', currency: 'INR', ruleset_version: 1, ruleset: ruleset as CircleView['ruleset'],
  members, rulesets: [{ version: 1, status: 'ACTIVE', fingerprint: 'f'.repeat(64), reason: 'initial ruleset', created_at: null }],
});
const cycleOf = (state: CycleView['state'], extra: Partial<CycleView> = {}): CycleView => ({
  id: 'cy1', circle_id: 'c1', number: 1, ruleset_version: 1, state, prior_state: null, due_date: '2030-01-10T12:00:00Z',
  payout_method: null, payout_mode: 'SEALED_BID_AUCTION', winner_member_id: null, discount: null, currency: 'INR',
  settlement_id: null, settlement_status: null, transitions: [],
  obligations: members.map((m) => ({ member_id: m.id, gross_due: 100_000, dividend_credit: 0, adjustments: 0, net_payable: 100_000, confirmed_paid: 0, outstanding: 100_000 })),
  ...extra,
});
const myCircle = (me: typeof ORG, state: CycleView['state']): MyCircle => ({
  id: 'c1', name: 'Family chit', organizer_id: 'org', my_role: me.id === 'org' ? 'organizer' : 'member',
  my_member_id: me.id === 'org' ? 'm1' : 'm2', currency: 'INR', total_chit_value: 400_000, member_count: 4, won_count: 0,
  payout_mode: 'SEALED_BID_AUCTION', pending_actions: 0,
  current_cycle: { id: 'cy1', number: 1, state, prior_state: null, due_date: '2030-01-10T12:00:00Z', ruleset_version: 1,
    payout_method: null, winner_member_id: null, discount: null, settlement_id: null, settlement_status: null,
    obligations_total: 4, obligations_settled: 1, outstanding_total: 300_000, my_outstanding: 100_000, my_net_payable: 100_000 },
});

let routes: Record<string, unknown> = {};
function serve(table: Record<string, unknown>) {
  routes = { '/config': { environment: 'development', sandbox_tools: true, payment_gateway: 'mock' }, ...table };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.replace('/api/backend', '').split('?')[0];
    const body = routes[path];
    return body === undefined
      ? new Response(JSON.stringify({ detail: `no mock for ${path}` }), { status: 404 })
      : new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
}
const signIn = (user = ORG) => window.localStorage.setItem('chitcircle.auth.v1',
  JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 3_600_000, user }));
const wrap = (ui: ReactNode) => render(
  <ThemeProvider><SessionProvider><ToastProvider><AppShell>{ui}</AppShell></ToastProvider></SessionProvider></ThemeProvider>);

beforeEach(() => {
  nav.replace.mockReset(); nav.push.mockReset(); nav.params = {}; nav.search = new URLSearchParams(); nav.path = '/app/home';
  serve({ '/auth/me': ORG });
});

describe('app shell', () => {
  it('sends signed-out visitors to /welcome', async () => {
    wrap(<div>secret</div>);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/welcome'));
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });
  it('shows the main navigation with the current section marked', async () => {
    signIn(); nav.path = '/app/circles';
    wrap(<div>content</div>);
    const navs = screen.getAllByRole('navigation', { name: 'Main' });
    const bottom = navs[navs.length - 1];
    expect(within(bottom).getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Circles', 'Activity', 'Profile']);
    expect(within(bottom).getByText('Circles').closest('a')).toHaveAttribute('aria-current', 'page');
  });
});

describe('sign in', () => {
  it('exchanges email + password for a session', async () => {
    serve({ '/auth/login': { access_token: 'jwt', token_type: 'bearer', user_id: 'org', role: 'member', expires_in: 3600, user: ORG } });
    render(<ThemeProvider><SessionProvider><SignIn /></SessionProvider></ThemeProvider>);
    await userEvent.type(screen.getByLabelText('Email'), 'org@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/app/home'));
    expect(JSON.parse(window.localStorage.getItem('chitcircle.auth.v1')!).token).toBe('jwt');
  });
});

describe('home', () => {
  it('shows an empty state with no circles', async () => {
    signIn(); serve({ '/auth/me': ORG, '/circles': [] });
    wrap(<HomePage />);
    expect(await screen.findByText('No circles yet')).toBeInTheDocument();
  });
  it('lists what needs attention and the circle card', async () => {
    signIn(); serve({ '/auth/me': ORG, '/circles': [myCircle(ORG, 'COLLECTIONS_IN_PROGRESS')] });
    wrap(<HomePage />);
    expect(await screen.findByText('Open the auction')).toBeInTheDocument();
    expect(screen.getByText('Family chit')).toBeInTheDocument();
    expect(screen.getByText('You’re all paid up')).toBeInTheDocument();   // auction installments are not payable yet
  });
  it('circles list filters by role', async () => {
    signIn(); serve({ '/auth/me': ORG, '/circles': [myCircle(ORG, 'DRAFT')] });
    nav.path = '/app/circles';
    wrap(<CirclesPage />);
    expect(await screen.findByText('Family chit')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: /^Member/ }));
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });
});

describe('circle workspace', () => {
  it('shows members with link status for the organizer', async () => {
    signIn(); nav.params = { circleId: 'c1' };
    const dashboard = {
      circle_id: 'c1', circle_name: 'Family chit',
      summary: { total_members: 4, won_members: 0, remaining_members: 4, total_cycles: 0, completed_cycles: 0,
        current_cycle_id: null, current_cycle_number: 0, current_cycle_state: null, current_cycle_due_date: null },
      collections: { collected: 0, outstanding: 0, late: 0, total_members: 0, amount_collected: 0, amount_outstanding: 0 },
      auctions: { completed: 0, pending: 0, current_state: null }, payouts: { completed: 0, pending: 0, failed: 0 },
      risk: { late_members_count: 0, late_members: [] }, security: { pending: 0, verified: 0 }, recent_activity: [],
    };
    serve({ '/auth/me': ORG, '/circles/c1': circleFor(ORG), '/circles/c1/cycles': [], '/circles/c1/dashboard': dashboard });
    wrap(<CirclePage />);
    expect(await screen.findByRole('heading', { name: 'Family chit' })).toBeInTheDocument();
    expect(screen.getByText('Start round 1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Members' }));
    expect(screen.getByText('Ravi Kumar')).toBeInTheDocument();
    expect(screen.getAllByText(/Account linked/).length).toBe(2);
    expect(screen.getByLabelText('Security status for Joe')).toBeInTheDocument();
  });
});

describe('round workspace', () => {
  it('organizer gets the next step for the round', async () => {
    signIn(); nav.params = { circleId: 'c1', cycleId: 'cy1' };
    serve({ '/auth/me': ORG, '/circles/c1': circleFor(ORG), '/cycles/cy1': cycleOf('COLLECTIONS_IN_PROGRESS'),
      '/cycles/cy1/ledger': { items: [], next_cursor: null, has_more: false } });
    wrap(<RoundPage />);
    expect(await screen.findByRole('button', { name: 'Open the auction' })).toBeInTheDocument();
    expect(screen.getByText(/Installments are finalized after the auction settles/)).toBeInTheDocument();
  });
  it('a member can bid while the auction is open, with the advisor preview', async () => {
    signIn(MEM); nav.params = { circleId: 'c1', cycleId: 'cy1' };
    serve({ '/auth/me': MEM, '/circles/c1': circleFor(MEM), '/cycles/cy1': cycleOf('AUCTION_OPEN'), '/cycles/cy1/auction/bids': [],
      '/cycles/cy1/ledger': { items: [], next_cursor: null, has_more: false },
      '/cycles/cy1/members/m2/explanation': { member_id: 'm2', cycle_id: 'cy1', currency: 'INR', is_winner: false, lines: [], summary: 'x', source_event_ids: [] },
      '/cycles/cy1/auction/preview': { member_id: 'm2', currency: 'INR', discount_minor: 4_000_000, reasons: [], valid: true,
        chit_value_minor: 400_000, cap_minor: 120_000, min_discount_minor: 0, increment_minor: 0, discount_rate: '10.0%',
        preview: { you_receive_minor: 360_000, commission_minor: 20_000, dividend_pool_minor: 20_000, your_dividend_minor: 5_000, your_net_contribution_minor: 95_000 },
        history: [], note: 'No earlier auctions in this circle to compare with yet.' } });
    wrap(<RoundPage />);
    const input = await screen.findByLabelText('Your discount bid');
    await userEvent.type(input, '400');
    expect(await screen.findByText('You would receive')).toBeInTheDocument();
    expect(screen.getByText('₹3,600')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Place bid' })).toBeEnabled();
  });
});

describe('settlement', () => {
  it('lets the organizer approve a settlement awaiting approval', async () => {
    signIn(); nav.params = { settlementId: 's1' };
    const m = (minor: number) => ({ minor, currency: 'INR' });
    const ids = members.map((x) => x.id);
    const st: SettlementView = {
      id: 's1', cycle_id: 'cy1', status: 'CALCULATED', ruleset_version: 1, provider_payout_ref: null, payout_reference: 'payout:s1',
      payout_requested_at: null, finalized_at: null, circle_id: 'c1', circle_name: 'Family chit', organizer_id: 'org', cycle_number: 1,
      cycle_state: 'AWAITING_APPROVAL', prior_state: null, state_reason: null, required_approvals: 1, require_security: false,
      require_full_collection_before_payout: true, winner_security_status: 'NONE', approvals: [],
      settlement: { circle_id: 'c1', cycle_id: 'cy1', ruleset_version: 1, ruleset_fingerprint: 'f'.repeat(64), currency: 'INR',
        payout_method: 'SEALED_BID_AUCTION', winner_member_id: 'm2', member_order: ids, chit_value: m(400_000), discount: m(40_000),
        winner_payout: m(360_000), commission: m(20_000), dividend_pool: m(20_000),
        contributions: Object.fromEntries(ids.map((i) => [i, m(100_000)])), dividends: Object.fromEntries(ids.map((i) => [i, m(5_000)])),
        net_contributions: Object.fromEntries(ids.map((i) => [i, m(95_000)])), rounding_remainder: m(0), remainder_destination: null, adjustments: [] },
    };
    serve({ '/auth/me': ORG, '/settlements/s1': st, '/circles/c1': circleFor(ORG) });
    wrap(<SettlementPage />);
    expect(await screen.findByRole('button', { name: 'Approve settlement' })).toBeInTheDocument();
    expect(screen.getAllByText('₹3,600.00').length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: 'Approve settlement' }));
    expect(await screen.findByRole('dialog', { name: 'Approve settlement' })).toBeInTheDocument();
  });
});

describe('profile', () => {
  it('persists the theme and signs out', async () => {
    signIn(); wrap(<ProfilePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dark' }));
    expect(window.localStorage.getItem('chitcircle.theme')).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: /sign out/i }));
    expect(window.localStorage.getItem('chitcircle.auth.v1')).toBeNull();
    expect(nav.replace).toHaveBeenCalledWith('/welcome');
  });
});
