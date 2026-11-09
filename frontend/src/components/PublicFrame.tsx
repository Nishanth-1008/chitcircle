'use client';
import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useSession } from '@/lib/session';
import { Icon, type IconName } from './Icon';
import { Wordmark } from './ui';

const POINTS: { icon: IconName; title: string; body: string }[] = [
  { icon: 'scale', title: 'Rules before AI', body: 'Settlements, dividends and bid checks come from a tested engine, never a model.' },
  { icon: 'receipt', title: 'One shared record', body: 'Every contribution and payout lands in an append-only, double-entry ledger.' },
  { icon: 'shield', title: 'People approve money', body: 'Agents draft reminders and invoices; nothing moves without your step-up approval.' },
];

/** Split layout for signed-out screens. Signed-in visitors are sent to the app. */
export function PublicFrame({ children }: { children: ReactNode }) {
  const { ready, user } = useSession();
  const router = useRouter();
  useEffect(() => { if (ready && user) router.replace('/app/home'); }, [ready, user, router]);
  return (
    <div className="public">
      <aside className="public__hero">
        <Wordmark large />
        <div className="stack stack--lg" style={{ position: 'relative', zIndex: 1 }}>
          <h2>Run your savings circle without the spreadsheet.</h2>
          <p>Collections, auctions, payouts and records for chit funds, tandas, susus and committees, in one place your members can check.</p>
          <div className="hero-points">
            {POINTS.map((p) => (
              <div key={p.title} className="hero-point">
                <span><Icon name={p.icon} /></span>
                <div><b>{p.title}</b><small>{p.body}</small></div>
              </div>
            ))}
          </div>
        </div>
        <small style={{ opacity: 0.75, position: 'relative', zIndex: 1 }}>
          Software for organizers. ChitCircle never holds member funds; payments run through PayPal.
        </small>
      </aside>
      <main className="public__panel">{children}</main>
    </div>
  );
}
