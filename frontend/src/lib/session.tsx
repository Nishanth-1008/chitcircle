'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { UNAUTHORIZED_EVENT, type ApiContext } from './api/client';
import { api } from './api/endpoints';
import { readStorage, writeStorage } from './storage';
import type { TokenResponse, UserView } from './types';

const KEY = 'chitcircle.auth.v1';
/** Refresh this long before the token expires. */
const REFRESH_MARGIN_MS = 5 * 60_000;

export interface StoredAuth { token: string; expiresAt: number; user: UserView }

interface SessionValue extends ApiContext {
  ready: boolean;
  user: UserView | null;
  signIn: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; name: string }) => Promise<void>;
  signOut: () => void;
  setUser: (u: UserView) => void;
}

const Ctx = createContext<SessionValue | null>(null);

export function parseStored(raw: string | null, now = Date.now()): StoredAuth | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<StoredAuth>;
    if (typeof v.token !== 'string' || typeof v.expiresAt !== 'number' || !v.user || typeof v.user.id !== 'string') return null;
    if (v.expiresAt <= now) return null;
    return v as StoredAuth;
  } catch { return null; }
}

export const fromToken = (t: TokenResponse, now = Date.now()): StoredAuth =>
  ({ token: t.access_token, expiresAt: now + t.expires_in * 1000, user: t.user });

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [auth, setAuth] = useState<StoredAuth | null>(null);
  const authRef = useRef<StoredAuth | null>(null);

  const commit = useCallback((next: StoredAuth | null) => {
    authRef.current = next;
    setAuth(next);
    writeStorage(KEY, next ? JSON.stringify(next) : null);
  }, []);

  useEffect(() => {
    const stored = parseStored(readStorage(KEY));
    authRef.current = stored;
    setAuth(stored);
    setReady(true);
    if (stored) {
      api.me({ token: stored.token }).then(
        (user) => authRef.current && commit({ ...authRef.current, user }),
        () => undefined,
      );
    }
  }, [commit]);

  useEffect(() => {
    const onUnauthorized = () => commit(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [commit]);

  useEffect(() => {
    if (!auth) return;
    const wait = Math.max(5_000, auth.expiresAt - Date.now() - REFRESH_MARGIN_MS);
    const t = window.setTimeout(() => {
      api.refresh({ token: auth.token }).then((r) => commit(fromToken(r)), () => undefined);
    }, wait);
    return () => window.clearTimeout(t);
  }, [auth, commit]);

  const value = useMemo<SessionValue>(() => ({
    ready,
    token: auth?.token ?? null,
    user: auth?.user ?? null,
    signIn: async (email, password) => commit(fromToken(await api.login(email.trim(), password))),
    register: async (data) => commit(fromToken(await api.register({ ...data, email: data.email.trim() }))),
    signOut: () => commit(null),
    setUser: (user) => authRef.current && commit({ ...authRef.current, user }),
  }), [ready, auth, commit]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSession must be used inside <SessionProvider>');
  return v;
}

/** Stable key prefix so cached resources never leak across identities. */
export const sessionKey = (s: { user: UserView | null }) => s.user?.id ?? 'anon';
