'use client';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { readStorage, writeStorage } from './storage';

export type ThemePref = 'system' | 'light' | 'dark';
const KEY = 'chitcircle.theme';

/** Runs before first paint (inlined in <head>) so there is no light-to-dark flash. Keep in sync with resolve(). */
export const THEME_INIT_SCRIPT = `(function(){try{var p=localStorage.getItem('${KEY}')||'system';var d=p==='dark'||(p==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=d?'dark':'light';}catch(e){document.documentElement.dataset.theme='light';}})();`;

export function resolveTheme(pref: ThemePref, systemDark: boolean): 'light' | 'dark' {
  return pref === 'dark' || (pref === 'system' && systemDark) ? 'dark' : 'light';
}

interface ThemeValue { pref: ThemePref; resolved: 'light' | 'dark'; setPref: (p: ThemePref) => void }
const Ctx = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>('system');
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    const stored = readStorage(KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') setPrefState(stored);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    setSystemDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const resolved = resolveTheme(pref, systemDark);
  useEffect(() => { document.documentElement.dataset.theme = resolved; }, [resolved]);

  const setPref = useCallback((p: ThemePref) => { setPrefState(p); writeStorage(KEY, p); }, []);
  return <Ctx.Provider value={{ pref, resolved, setPref }}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useTheme must be used inside <ThemeProvider>');
  return v;
}
