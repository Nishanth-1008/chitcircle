'use client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Banner, Button, Wordmark } from '@/components/ui';
import { useSession } from '@/lib/session';

const ROLES = ['member', 'organizer', 'approver'] as const;

/**
 * DEVELOPMENT-ONLY sign-in. The backend currently identifies callers by X-Actor-Id / X-Actor-Role headers, which any
 * client can forge. This screen exists so the app can talk to a local backend. Replace with real authentication
 * (session/JWT issued by the server) before any deployment.
 */
export default function DevSignIn() {
  const router = useRouter();
  const { signInDev, liveAvailable } = useSession();
  const [actorId, setActorId] = useState('');
  const [role, setRole] = useState<string>('member');
  const [error, setError] = useState('');

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!actorId.trim()) { setError('Enter the actor ID your backend should treat you as.'); return; }
    signInDev(actorId, role);
    router.push('/app/home');
  }

  return (
    <div className="frame"><div className="app">
      <main className="screen screen--plain" style={{ paddingTop: 48 }}>
        <Wordmark large />
        <h1>Development sign-in</h1>
        <Banner tone="warning" icon="alert">
          <strong>Not real authentication.</strong> The backend trusts the ID and role you type here. Never use this in production.
        </Banner>
        {!liveAvailable && <Banner tone="info">The live API isn’t configured. Set <code>NEXT_PUBLIC_LIVE_API_ENABLED=true</code> and <code>CHITCIRCLE_API_URL</code>.</Banner>}
        <form className="stack stack--lg" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="actor">Actor ID</label>
            <input id="actor" value={actorId} onChange={(e) => { setActorId(e.target.value); setError(''); }}
                   autoComplete="off" aria-invalid={!!error} aria-describedby="actor-help" />
            <span id="actor-help" className={error ? 'field__error' : 'field__help'}>
              {error || 'For members this is the member ID; for organizers it is the organizer ID used when creating the circle.'}
            </span>
          </div>
          <div className="field">
            <label htmlFor="role">Header role</label>
            <select id="role" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <span className="field__help">Sent as X-Actor-Role. The app never uses it to decide what you may do; the server does.</span>
          </div>
          <Button block type="submit" disabled={!liveAvailable}>Continue</Button>
          <Button block variant="ghost" onClick={() => router.push('/welcome')}>Back</Button>
        </form>
      </main>
    </div></div>
  );
}
