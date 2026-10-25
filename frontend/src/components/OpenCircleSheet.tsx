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
  const [circleId, setCircleId] = useState('');
  const [error, setError] = useState('');

  const { run, pending } = useSingleFlight(async () => {
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

  return (
    <BottomSheet open={open} title="Open a circle" onClose={onClose}>
      <form className="stack stack--lg" onSubmit={(e) => { e.preventDefault(); void run(); }} noValidate>
        <div className="field">
          <label htmlFor="circle-id">Circle ID</label>
          <input id="circle-id" value={circleId} onChange={(e) => { setCircleId(e.target.value); setError(''); }}
                 autoComplete="off" autoCapitalize="off" spellCheck={false} aria-invalid={!!error} aria-describedby="circle-id-msg" />
          <span id="circle-id-msg" className={error ? 'field__error' : 'field__help'} role={error ? 'alert' : undefined}>
            {error || 'Ask the organizer for the circle ID.'}
          </span>
        </div>
        <Banner tone="neutral">Circles you open are remembered on this device only. An account-wide list needs a backend update.</Banner>
        <Button block type="submit" disabled={pending}>{pending ? 'Checking…' : 'Open circle'}</Button>
      </form>
    </BottomSheet>
  );
}
