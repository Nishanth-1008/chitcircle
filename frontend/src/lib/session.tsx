'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { ApiContext, DataMode } from './api/client';
import { DEMO_ACTOR } from './api/demo';
import { LIVE_API_ENABLED } from './config';
import type { Actor } from './permissions';
import { readStorage, writeStorage } from './storage';

const KEY = 'chitcircle.session.v1';

interface Stored { mode: DataMode; actor: Actor | null }

interface SessionValue extends ApiContext {
  ready: boolean;
  liveAvailable: boolean;
  startDemo: () => void;
  /** DEVELOPMENT ONLY. The backend currently trusts these headers; there is no real authentication yet. */
  signInDev: (actorId: string, role: string) => void;
  signOut: () => void;
}

const Ctx = createContext<SessionValue | null>(null);

export function parseStored(raw: string | null): Stored | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<Stored>;
    if (v.mode !== 'demo' && v.mode !== 'live') return null;
    if (v.actor && (typeof v.actor.id !== 'string' || typeof v.actor.role !== 'string')) return null;
    if (v.mode === 'live' && !LIVE_API_ENABLED) return null;
    return { mode: v.mode, actor: v.actor ?? null };
  } catch { return null; }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [state, setState] = useState<Stored>({ mode: 'demo', actor: null });

  useEffect(() => {
    const stored = parseStored(readStorage(KEY));
    if (stored) setState(stored);
    setReady(true);
  }, []);

  const commit = useCallback((next: Stored) => {
    setState(next);
    writeStorage(KEY, JSON.stringify(next));
  }, []);

  const value = useMemo<SessionValue>(() => ({
    ready,
    mode: state.mode,
    actor: state.actor,
    liveAvailable: LIVE_API_ENABLED,
    startDemo: () => commit({ mode: 'demo', actor: { ...DEMO_ACTOR } }),
    signInDev: (actorId, role) => commit({ mode: 'live', actor: { id: actorId.trim(), role } }),
    signOut: () => { setState({ mode: 'demo', actor: null }); writeStorage(KEY, null); },
  }), [ready, state, commit]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSession must be used inside <SessionProvider>');
  return v;
}

/** Stable per-session key prefix so cached/fetched resources never leak across identities or modes. */
export function sessionKey(ctx: ApiContext): string {
  return `${ctx.mode}:${ctx.actor?.id ?? 'anon'}`;
}
