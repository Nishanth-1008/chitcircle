'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Icon } from '@/components/Icon';
import { Button, Wordmark } from '@/components/ui';
import { useSession } from '@/lib/session';

export default function Welcome() {
  const router = useRouter();
  const { startDemo, liveAvailable } = useSession();
  return (
    <div className="frame"><div className="app">
      <main className="welcome">
        <div><Wordmark large /></div>
        <div className="welcome__marks" aria-label="What ChitCircle helps with">
          <div className="welcome__mark"><span><Icon name="calendar" /></span>Clear schedules</div>
          <div className="welcome__mark"><span><Icon name="receipt" /></span>Shared records</div>
          <div className="welcome__mark"><span><Icon name="scale" /></span>Open rules</div>
        </div>
        <div>
          <h1>Community savings, made simpler.</h1>
          <p className="lead">Manage circles, contributions, and payouts in one place.</p>
        </div>
        <div className="stack">
          <Button block onClick={() => { startDemo(); router.push('/app/home'); }}>Explore the demo</Button>
          {liveAvailable
            ? <Link href="/sign-in" className="btn btn--secondary btn--block">Sign in (development)</Link>
            : <Button block variant="secondary" disabled>Sign in isn’t available yet</Button>}
          <p className="muted" style={{ fontSize: 12 }}>
            Account sign-up needs the authentication service, which isn’t built yet. The demo uses fictional data and no real money moves.
          </p>
        </div>
      </main>
    </div></div>
  );
}
