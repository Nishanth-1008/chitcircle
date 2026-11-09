import { describe, expect, it } from 'vitest';
import { addCircle, addRound, latestRoundFor, parseSaved, removeCircle } from '@/lib/saved';
import { parseStored } from '@/lib/session';
import { resolveTheme } from '@/lib/theme';

describe('saved items', () => {
  const empty = { circles: [], rounds: [] };
  it('starts empty with nothing saved', () => {
    expect(parseSaved(null).circles.length).toBe(0);
    expect(parseSaved(null).rounds.length).toBe(0);
  });
  it('survives corrupt storage', () => {
    expect(parseSaved('{oops')).toEqual(empty);
    expect(parseSaved('{"circles":[1,null,{"id":"a"}],"rounds":"x"}')).toEqual({ circles: [{ id: 'a' }], rounds: [] });
  });
  it('adds without duplicates and links rounds to their circle', () => {
    let s = addCircle(empty, 'c1', 1);
    s = addCircle(s, 'c1', 2);
    expect(s.circles).toHaveLength(1);
    s = addRound(s, 'r1', 'c2', 3);
    s = addRound(s, 'r1', 'c2', 4);
    expect(s.circles.map((c) => c.id)).toEqual(['c2', 'c1']);
    expect(s.rounds).toHaveLength(1);
    expect(latestRoundFor(s, 'c2')?.id).toBe('r1');
  });
  it('removing a circle removes its rounds', () => {
    const s = removeCircle(addRound(addCircle(empty, 'c1', 1), 'r1', 'c1', 2), 'c1');
    expect(s).toEqual(empty);
  });
});

describe('session + theme parsing', () => {
  it('rejects malformed sessions', () => {
    expect(parseStored(null)).toBeNull();
    expect(parseStored('nope')).toBeNull();
    expect(parseStored('{"actor":null}')).toEqual({ actor: null });
    expect(parseStored('{"actor":{"id":1}}')).toBeNull();
  });
  it('accepts a session with an actor', () => {
    expect(parseStored('{"actor":{"id":"a","role":"member"}}')?.actor?.id).toBe('a');
  });
  it('resolves theme preference', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
  });
});
