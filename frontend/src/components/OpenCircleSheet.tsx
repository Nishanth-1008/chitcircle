'use client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api } from '@/lib/api/endpoints';
import { describeError } from '@/lib/api/errors';
import { useSingleFlight } from '@/lib/hooks';
import { useSaved } from '@/lib/saved';
import { useSession } from '@/lib/session';
import { Banner, BottomSheet, Button } from './ui';

/**
 * The backend has no "list my circles" or invite/join endpoint yet, so people add a circle by its ID.
 * We verify it with GET /circles/{id} (the server decides whether this account may see it) before saving it
 * to this device.
 */
export function OpenCircleSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const ctx = useSession();
  const saved = useSaved(ctx.mode);
  const [tab, setTab] = useState<'open' | 'create'>('open');
  const [circleId, setCircleId] = useState('');
  const [error, setError] = useState('');

  // Create circle fields
  const [name, setName] = useState('');
  const [members, setMembers] = useState('Alice, Bob, Charlie');
  const [totalValue, setTotalValue] = useState(100000); // 1,00,000 INR

  const openAction = useSingleFlight(async () => {
    const id = circleId.trim();
    if (!id) { setError('Enter a circle ID.'); return; }
    setError('');
    try {
      const circle = await api.getCircle(ctx, id);
      saved.saveCircle(circle.id);
      onClose();
      setCircleId('');
      router.push(`/app/circles/${encodeURIComponent(circle.id)}`);
    } catch (e) {
      setError(describeError(e).message);
    }
  });

  const createAction = useSingleFlight(async () => {
    if (!name.trim()) { setError('Enter a circle name.'); return; }
    if (ctx.mode !== 'live') { setError('Creating circles is only supported in Live mode.'); return; }
    setError('');

    const memberList = members.split(',').map((s) => s.trim()).filter(Boolean);
    const actorId = ctx.actor?.id || 'organizer';
    if (!memberList.includes(actorId)) {
      memberList.unshift(actorId);
    }

    const valueMinor = Math.round(Number(totalValue) * 100);
    const payload = {
      name: name.trim(),
      ruleset: {
        currency: 'INR',
        total_chit_value: valueMinor,
        member_count: memberList.length,
        payout_mode: 'SEALED_BID_AUCTION',
        commission: { base: 'PERCENT_OF_CHIT_VALUE', rate: '0.05', rounding: 'HALF_UP' },
        dividend: { allocation: 'ALL_MEMBERS' },
        auction: { max_discount_rate: '0.40', min_discount: 0, increment: 0, tie_break: 'EARLIEST_BID', no_bid_fallback: 'HOLD' },
        grace_period_days: 5,
        rounding: { contribution_remainder: 'REJECT', remainder_destination: null },
        required_approvals: 1,
        require_security: false,
        jurisdiction_profile: 'IN-SANDBOX',
        effective_date: new Date().toISOString().slice(0, 10),
        status: 'ACTIVE',
      },
      members: memberList,
    };

    try {
      const created = await api.createCircle(ctx, payload);
      saved.saveCircle(created.id);
      onClose();
      setName('');
      router.push(`/app/circles/${encodeURIComponent(created.id)}`);
    } catch (e) {
      setError(describeError(e).message);
    }
  });

  return (
    <BottomSheet open={open} title={tab === 'open' ? 'Open a circle' : 'Create a circle'} onClose={onClose}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Button variant={tab === 'open' ? 'primary' : 'ghost'} small onClick={() => { setTab('open'); setError(''); }}>
          Open by ID
        </Button>
        <Button variant={tab === 'create' ? 'primary' : 'ghost'} small onClick={() => { setTab('create'); setError(''); }}>
          Create New Circle
        </Button>
      </div>

      {tab === 'open' ? (
        <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void openAction.run(); }} noValidate>
          <div className="field">
            <label htmlFor="circle-id">Circle ID</label>
            <input id="circle-id" value={circleId} onChange={(e) => { setCircleId(e.target.value); setError(''); }}
                   autoComplete="off" autoCapitalize="off" spellCheck={false} aria-invalid={!!error} aria-describedby="circle-id-msg" />
            <span id="circle-id-msg" className={error ? 'field__error' : 'field__help'} role={error ? 'alert' : undefined}>
              {error || 'Ask the organizer for the circle ID.'}
            </span>
          </div>
          <Banner tone="neutral">Circles you open are remembered on this device only.</Banner>
          <Button block type="submit" disabled={openAction.pending}>{openAction.pending ? 'Checking…' : 'Open circle'}</Button>
        </form>
      ) : (
        <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void createAction.run(); }} noValidate>
          <div className="field">
            <label htmlFor="circle-name">Circle Name</label>
            <input id="circle-name" value={name} onChange={(e) => { setName(e.target.value); setError(''); }} placeholder="e.g. Family Savings #1" />
          </div>
          <div className="field">
            <label htmlFor="total-value">Total Chit Pool (INR)</label>
            <input id="total-value" type="number" value={totalValue} onChange={(e) => setTotalValue(Number(e.target.value))} />
            <span className="field__help">Total pool distributed across members.</span>
          </div>
          <div className="field">
            <label htmlFor="circle-members">Members (comma-separated)</label>
            <input id="circle-members" value={members} onChange={(e) => setMembers(e.target.value)} />
            <span className="field__help">You are automatically added as the organizer.</span>
          </div>
          {error && <Banner tone="danger">{error}</Banner>}
          <Button block type="submit" disabled={createAction.pending}>{createAction.pending ? 'Creating…' : 'Create Circle on Server'}</Button>
        </form>
      )}
    </BottomSheet>
  );
}
