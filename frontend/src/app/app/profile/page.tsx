'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Avatar, Banner, Button, StatusPill } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { useSingleFlight } from '@/lib/hooks';
import { useSaved } from '@/lib/saved';
import { useSession } from '@/lib/session';
import { useTheme, type ThemePref } from '@/lib/theme';

const THEMES: { id: ThemePref; label: string }[] = [
  { id: 'system', label: 'System' }, { id: 'light', label: 'Light' }, { id: 'dark', label: 'Dark' },
];

export default function ProfilePage() {
  const router = useRouter();
  const ctx = useSession();
  const { pref, setPref } = useTheme();
  const saved = useSaved(ctx.mode);
  const [health, setHealth] = useState<{ ok: boolean; text: string } | null>(null);

  const check = useSingleFlight(async () => {
    try {
      const h = await api.health(ctx);
      setHealth({ ok: true, text: `Reachable (${h.status})` });
    } catch (e) { setHealth({ ok: false, text: describeError(e).message }); }
  });

  return (
    <Screen title="Profile">
      <section className="card row" aria-label="Account">
        <Avatar name={ctx.actor?.displayName ?? ctx.actor?.id ?? '?'} />
        <div className="grow">
          <p style={{ fontWeight: 700 }}>{ctx.actor?.displayName ?? 'Signed in'}</p>
          <p className="muted num" style={{ overflowWrap: 'anywhere' }}>ID {ctx.actor?.id}</p>
        </div>
        <StatusPill tone={ctx.mode === 'demo' ? 'warning' : 'info'}>{ctx.mode === 'demo' ? 'Demo data' : 'Live API'}</StatusPill>
      </section>

      {ctx.mode === 'live' && (
        <Banner tone="warning" icon="alert"><strong>Development identity.</strong> The backend trusts the ID and role sent by this browser. Replace with real authentication before deployment.</Banner>
      )}

      <section className="card stack" aria-label="Appearance">
        <h3>Theme</h3>
        <div className="segmented" role="group" aria-label="Theme">
          {THEMES.map((t) => <button key={t.id} type="button" aria-pressed={pref === t.id} onClick={() => setPref(t.id)}>{t.label}</button>)}
        </div>
        <p className="muted">Saved on this device. “System” follows your phone’s setting.</p>
      </section>

      <section className="card stack" aria-label="Data on this device">
        <h3>Saved on this device</h3>
        <p className="muted">{saved.items.circles.length} circle{saved.items.circles.length === 1 ? '' : 's'}, {saved.items.rounds.length} round{saved.items.rounds.length === 1 ? '' : 's'}. These shortcuts live in this browser only; they are not account settings.</p>
        <div className="row">
          {ctx.mode === 'demo' && <Button variant="secondary" small onClick={saved.resetToDefault}>Reset demo data</Button>}
          <Button variant="secondary" small onClick={saved.clear}>Clear saved</Button>
        </div>
      </section>

      {ctx.mode === 'live' && (
        <section className="card stack" aria-label="Connection">
          <h3>Connection</h3>
          <Button variant="secondary" small onClick={() => void check.run()} disabled={check.pending}>{check.pending ? 'Checking…' : 'Check API'}</Button>
          {health && <p className={health.ok ? 'amount--income' : 'field__error'} role="status">{health.text}</p>}
        </section>
      )}

      <section className="card" aria-label="More">
        <div className="link-list">
          <Link href="/app/help">Help &amp; what’s connected <Icon name="chevronRight" /></Link>
        </div>
      </section>

      <Button variant="secondary" block icon="signOut" onClick={() => { ctx.signOut(); router.replace('/welcome'); }}>Sign out</Button>
    </Screen>
  );
}
