import { Screen } from '@/components/shell';
import { Card } from '@/components/ui';

const FAQ: { q: string; a: string }[] = [
  { q: 'What is a savings circle?', a: 'A group agrees to contribute a fixed amount every round. Each round one member receives the whole pot, until everyone has received it once. Chit funds, tandas, susus, ROSCAs and committees are all versions of this.' },
  { q: 'How does the auction work?', a: 'In auction circles, members who have not received the pot yet bid the discount they are willing to give up. The highest valid discount wins. The recipient gets the pot minus the discount; the discount minus the organizer’s commission is shared back to members as a dividend, which lowers everyone’s installment for that round.' },
  { q: 'Why can’t I pay before the auction?', a: 'Your installment depends on the dividend, which is only known once the auction settles. Paying the full share earlier would overpay, and the round could not be reconciled until it was refunded.' },
  { q: 'When does my contribution count as paid?', a: 'Only when the payment provider confirms it to ChitCircle. Starting a PayPal payment or being invoiced does not count by itself. In the sandbox, “Simulate confirmed payment” sends a labelled sandbox confirmation through the same pipeline.' },
  { q: 'Who decides the winner and the numbers?', a: 'A deterministic settlement engine applies the circle’s rules. The app only displays what the engine calculated; no amount is computed in your browser or by an AI model.' },
  { q: 'What do the agents do?', a: 'The collections agent checks who owes money and proposes reminders or catch-up invoices on a fixed schedule. The explainer breaks down your installment from the ledger, and the bid advisor shows what a bid would mean for you. Agents never move money: the organizer approves each action with verification, which issues a single-use mandate.' },
  { q: 'Why can’t I see other members’ bids?', a: 'In sealed-bid circles, bids stay hidden until the auction closes so nobody can react to anyone else’s bid.' },
  { q: 'Can a record be changed?', a: 'No. The ledger is append-only. Corrections are new linked entries, and a member can flag a round, which opens a dispute the organizer must resolve on the record.' },
  { q: 'Does ChitCircle hold our money?', a: 'No. ChitCircle is software for organizers. Payments run through PayPal; the circle’s funds never sit with ChitCircle.' },
];

const CONNECTED: [string, string][] = [
  ['Accounts, sign-in and invitations by email', 'Live'],
  ['Circles, rounds, members and rules', 'Live'],
  ['Sealed and open auctions with bid advisor', 'Live'],
  ['Settlement, approvals, payout and reconciliation', 'Live'],
  ['Shared ledger with journal postings', 'Live'],
  ['Collections agent, approvals and mandates', 'Live'],
  ['PayPal invoices and payouts', 'Sandbox (when credentials are configured)'],
  ['PayPal webhook confirmations', 'Needs a public webhook URL; locally, use sandbox simulation'],
  ['SMS / email reminder delivery', 'In-app only for now'],
];

export default function HelpPage() {
  return (
    <Screen title="Help & how it works" back={{ href: '/app/profile', label: 'Profile' }}>
      <div className="grid grid--main">
        <Card title="Frequently asked questions">
          <div>
            {FAQ.map((f) => (
              <details key={f.q} className="faq">
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </Card>
        <Card title="What’s connected">
          <ul className="list">
            {CONNECTED.map(([what, status]) => (
              <li key={what} className="list__row">
                <span className="grow">{what}</span>
                <span className="muted small right">{status}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </Screen>
  );
}
