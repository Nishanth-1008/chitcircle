'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { Screen } from '@/components/shell';
import { Avatar, Banner, Button, Card, Field, KeyValue, Pill } from '@/components/ui';
import { useAppConfig } from '@/lib/appConfig';
import { api } from '@/lib/api/endpoints';
import { errorMessage } from '@/lib/api/errors';
import { useAction } from '@/lib/hooks';
import { useSession } from '@/lib/session';
import { humanize } from '@/lib/status';
import { useTheme, type ThemePref } from '@/lib/theme';
import { useToast } from '@/lib/toast';

const THEMES: { id: ThemePref; label: string }[] = [{ id: 'system', label: 'System' }, { id: 'light', label: 'Light' }, { id: 'dark', label: 'Dark' }];

export default function ProfilePage() {
  const session = useSession();
  const router = useRouter();
  const toast = useToast();
  const { pref, setPref } = useTheme();
  const config = useAppConfig();
  const user = session.user!;
  const [email, setEmail] = useState(user.payout_email ?? '');
  const [health, setHealth] = useState<{ ok: boolean; text: string } | null>(null);

  const save = useAction(async () => {
    const u = await api.setPayoutEmail(session, email.trim());
    session.setUser(u);
    toast('PayPal email saved');
  });
  const check = useAction(async () => {
    try { const h = await api.health(session); setHealth({ ok: true, text: `Reachable (${h.status})` }); }
    catch (e) { setHealth({ ok: false, text: errorMessage(e) }); }
  });

  return (
    <Screen title="Profile">
      <div className="grid grid--2">
        <div className="stack stack--lg">
          <Card>
            <div className="row">
              <Avatar name={user.name} you />
              <div className="grow"><h2>{user.name}</h2><p className="muted">{user.email}</p></div>
              {user.role !== 'member' && <Pill tone="brand">{humanize(user.role)}</Pill>}
            </div>
          </Card>
          <Card title="PayPal account" subtitle="Where invoices are sent and payouts are paid. Use a PayPal sandbox personal account while testing.">
            <form className="stack" onSubmit={(e) => { e.preventDefault(); void save.run(); }}>
              <Field label="PayPal email">
                {(id) => <input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@personal.example.com" />}
              </Field>
              {user.payout_email && (
                <p className="small">{user.payout_email_verified ? <span className="income"><Icon name="checkCircle" width={14} height={14} /> Verified</span>
                  : <span className="muted">Not verified yet</span>}</p>
              )}
              {save.error && <Banner tone="danger">{save.error}</Banner>}
              <Button type="submit" small disabled={save.pending || !email.trim() || email.trim() === user.payout_email}>{save.pending ? 'Saving…' : 'Save'}</Button>
            </form>
          </Card>
          <Card title="Appearance">
            <div className="segmented" role="group" aria-label="Theme">
              {THEMES.map((t) => <button key={t.id} type="button" aria-pressed={pref === t.id} onClick={() => setPref(t.id)}>{t.label}</button>)}
            </div>
          </Card>
        </div>
        <div className="stack stack--lg">
          <Card title="Connection">
            <KeyValue rows={[
              ['Environment', config ? humanize(config.environment) : '…'],
              ['Payment gateway', config ? (config.payment_gateway === 'paypal' ? 'PayPal sandbox' : 'Mock (no PayPal credentials)') : '…'],
              ['Sandbox tools', config ? (config.sandbox_tools ? 'On' : 'Off') : '…'],
            ]} />
            <div className="row row--wrap">
              <Button variant="secondary" small icon="refresh" disabled={check.pending} onClick={() => void check.run()}>{check.pending ? 'Checking…' : 'Check API'}</Button>
              {health && <span className={health.ok ? 'income' : 'expense'}>{health.text}</span>}
            </div>
          </Card>
          <Card title="More">
            <Link href="/app/help" className="list__row"><Icon name="help" width={18} height={18} /><span className="grow">Help & how it works</span><Icon name="chevronRight" width={16} height={16} /></Link>
          </Card>
          <Button variant="secondary" block icon="signOut" onClick={() => { session.signOut(); router.replace('/welcome'); }}>Sign out</Button>
        </div>
      </div>
    </Screen>
  );
}
