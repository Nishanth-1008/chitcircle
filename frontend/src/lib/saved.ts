'use client';
/**
 * "Saved on this device" circles and rounds.
 *
 * WHY THIS EXISTS: the backend has no list endpoints (no GET /circles, no cycle list, no cross-circle feed).
 * Until it does, the only honest way to build Home / Circles / Activity is from IDs the user has explicitly opened
 * on this device. Each saved item is then loaded from the authoritative GET endpoints. Nothing here is account-wide
 * state and the UI says so.
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { DataMode } from './api/client';
import { DEMO_CIRCLE_IDS, DEMO_CYCLE_IDS } from './api/demo';
import { readStorage, writeStorage } from './storage';

export interface SavedCircle { id: string; savedAt: number }
export interface SavedRound { id: string; circleId: string; savedAt: number }
export interface SavedItems { circles: SavedCircle[]; rounds: SavedRound[] }

const keyFor = (mode: DataMode) => `chitcircle.saved.v1.${mode}`;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

const DEMO_DEFAULT: SavedItems = {
  circles: [
    { id: DEMO_CIRCLE_IDS.weekend, savedAt: 2 },
    { id: DEMO_CIRCLE_IDS.tech, savedAt: 1 },
  ],
  rounds: [
    { id: DEMO_CYCLE_IDS.weekend, circleId: DEMO_CIRCLE_IDS.weekend, savedAt: 2 },
    { id: DEMO_CYCLE_IDS.tech, circleId: DEMO_CIRCLE_IDS.tech, savedAt: 1 },
  ],
};
const EMPTY: SavedItems = { circles: [], rounds: [] };

export function parseSaved(raw: string | null, mode: DataMode): SavedItems {
  if (raw === null) return mode === 'demo' ? DEMO_DEFAULT : EMPTY;
  try {
    const v = JSON.parse(raw) as Partial<SavedItems>;
    const circles = Array.isArray(v.circles) ? v.circles.filter((c) => c && typeof c.id === 'string') : [];
    const rounds = Array.isArray(v.rounds)
      ? v.rounds.filter((r) => r && typeof r.id === 'string' && typeof r.circleId === 'string') : [];
    return { circles, rounds };
  } catch { return EMPTY; }
}

export function addCircle(items: SavedItems, id: string, now = Date.now()): SavedItems {
  if (items.circles.some((c) => c.id === id)) return items;
  return { ...items, circles: [{ id, savedAt: now }, ...items.circles] };
}
export function addRound(items: SavedItems, id: string, circleId: string, now = Date.now()): SavedItems {
  const withCircle = addCircle(items, circleId, now);
  if (withCircle.rounds.some((r) => r.id === id)) return withCircle;
  return { ...withCircle, rounds: [{ id, circleId, savedAt: now }, ...withCircle.rounds] };
}
export function removeCircle(items: SavedItems, id: string): SavedItems {
  return { circles: items.circles.filter((c) => c.id !== id), rounds: items.rounds.filter((r) => r.circleId !== id) };
}
export function latestRoundFor(items: SavedItems, circleId: string): SavedRound | undefined {
  return items.rounds.filter((r) => r.circleId === circleId).sort((a, b) => b.savedAt - a.savedAt)[0];
}

export function useSaved(mode: DataMode) {
  const subscribe = useCallback((cb: () => void) => {
    listeners.add(cb);
    window.addEventListener('storage', cb);
    return () => { listeners.delete(cb); window.removeEventListener('storage', cb); };
  }, []);
  const getSnapshot = useCallback(() => readStorage(keyFor(mode)) ?? `__unset__${mode}`, [mode]);
  const getServerSnapshot = () => `__unset__${mode}`;
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const items = useMemo(() => parseSaved(raw.startsWith('__unset__') ? null : raw, mode), [raw, mode]);

  const update = useCallback((fn: (cur: SavedItems) => SavedItems) => {
    const cur = parseSaved(readStorage(keyFor(mode)), mode);
    writeStorage(keyFor(mode), JSON.stringify(fn(cur)));
    emit();
  }, [mode]);

  return {
    items,
    saveCircle: useCallback((id: string) => update((c) => addCircle(c, id)), [update]),
    saveRound: useCallback((id: string, circleId: string) => update((c) => addRound(c, id, circleId)), [update]),
    forgetCircle: useCallback((id: string) => update((c) => removeCircle(c, id)), [update]),
    clear: useCallback(() => { writeStorage(keyFor(mode), JSON.stringify(EMPTY)); emit(); }, [mode]),
    resetToDefault: useCallback(() => { writeStorage(keyFor(mode), null); emit(); }, [mode]),
  };
}
