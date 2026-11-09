'use client';
import { Icon } from '@/components/Icon';
import { PublicFrame } from '@/components/PublicFrame';
import { LinkButton, Wordmark } from '@/components/ui';

export default function Welcome() {
  return (
    <PublicFrame>
      <div className="welcome">
        <Wordmark large />
        <div>
          <h1>Community savings, made simpler.</h1>
          <p className="lead">Organize a circle, collect contributions, run fair auctions and pay out the pot, with the math shown to every member.</p>
        </div>
        <div className="welcome__marks" aria-label="What ChitCircle helps with">
          <div className="welcome__mark"><span><Icon name="calendar" /></span>Clear schedules</div>
          <div className="welcome__mark"><span><Icon name="receipt" /></span>Shared records</div>
          <div className="welcome__mark"><span><Icon name="scale" /></span>Open rules</div>
        </div>
        <div className="stack">
          <LinkButton href="/register" block>Create an account</LinkButton>
          <LinkButton href="/sign-in" variant="secondary" block>Sign in</LinkButton>
        </div>
        <p className="muted small">Invited to a circle? Create an account with the email the organizer used and you’ll be linked to your seat automatically.</p>
      </div>
    </PublicFrame>
  );
}
