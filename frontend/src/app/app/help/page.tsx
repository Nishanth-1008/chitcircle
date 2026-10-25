'use client';
import { Screen } from '@/components/shell';
import { Banner, StatusPill } from '@/components/ui';
import { PAYOUT_GATEWAY } from '@/lib/config';

const FAQ = [
  ['What is a chit circle?', 'A group of members who contribute a fixed amount every round. Each round, one member receives the pot. The circle’s rules decide how that member is chosen: rotation, a lottery, or an auction.'],
  ['When does a contribution count as paid?', 'Only when the payment provider confirms it and the server records it. Tapping a button or being redirected is never treated as payment.'],
  ['Who decides auction winners and dividends?', 'The server. This app only displays what the server calculated; it never works out winners, dividends, commission or payouts itself.'],
  ['Why can’t I see other members’ bids?', 'In sealed-bid auctions, bids stay hidden until the auction closes.'],
  ['What does “Demo” mean?', 'Demo screens use fictional people and amounts so you can explore the layout. No real money moves.'],
];

type Row = { what: string; endpoint: string; ok: boolean; note?: string };
const CONNECTED: Row[] = [
  { what: 'View a circle and its members', endpoint: 'GET /circles/{id}', ok: true },
  { what: 'View a round and who has paid', endpoint: 'GET /cycles/{id}', ok: true },
  { what: 'Round ledger and activity', endpoint: 'GET /cycles/{id}/ledger', ok: true },
  { what: 'Auction bids (sealed bids stay hidden)', endpoint: 'GET /cycles/{id}/auction/bids', ok: true },
  { what: 'Settlement and reconciliation', endpoint: 'GET /settlements/{id}[/reconciliation]', ok: true },
  { what: 'List your circles / rounds / settlements', endpoint: 'not in backend', ok: false },
  { what: 'Sign up, sign in, profile', endpoint: 'not in backend', ok: false, note: 'Development identity only' },
  { what: 'Invitations and joining a circle', endpoint: 'not in backend', ok: false },
  { what: 'Pay a contribution online', endpoint: 'not in backend', ok: false },
  { what: 'Notifications', endpoint: 'not in backend', ok: false },
  { what: 'Combined activity feed, ledger event detail', endpoint: 'not in backend', ok: false },
  { what: 'Create circles, place bids, approve, pay out', endpoint: 'exists in backend', ok: false, note: 'Not in this release of the app' },
];

export default function HelpPage() {
  return (
    <Screen title="Help & support" back="/app/profile">
      <section className="card" aria-label="Frequently asked questions">
        {FAQ.map(([q, a]) => (
          <details className="faq" key={q}><summary>{q}</summary><p>{a}</p></details>
        ))}
      </section>

      <section className="card stack" aria-label="What is connected">
        <h2>What’s connected</h2>
        <p className="muted">This release is read-only. Features marked “Not connected” are waiting on the backend or a later release.</p>
        <table className="api-table">
          <tbody>
            {CONNECTED.map((r) => (
              <tr key={r.what}>
                <td><div style={{ fontWeight: 600 }}>{r.what}</div><code>{r.endpoint}</code>{r.note && <div className="muted">{r.note}</div>}</td>
                <td style={{ textAlign: 'right' }}><StatusPill tone={r.ok ? 'success' : 'neutral'}>{r.ok ? 'Connected' : 'Not connected'}</StatusPill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <Banner tone="warning" icon="alert">
        {PAYOUT_GATEWAY === 'stub'
          ? 'The payout provider integration is a stub. No payout status in this app should be read as real money having moved.'
          : 'A payout provider is configured. Payouts count only after the provider confirms them and reconciliation passes.'}
      </Banner>
      <Banner tone="neutral" icon="info">Need a person? A support channel hasn’t been set up yet.</Banner>
    </Screen>
  );
}
