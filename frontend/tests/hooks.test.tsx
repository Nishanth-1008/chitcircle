import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api/errors';
import { useApi, useSingleFlight } from '@/lib/hooks';

describe('useSingleFlight (duplicate-submit prevention)', () => {
  it('ignores repeated calls while one is in flight, even in the same tick', async () => {
    let release!: () => void;
    const fn = vi.fn(() => new Promise<string>((res) => { release = () => res('done'); }));
    const { result } = renderHook(() => useSingleFlight(fn));
    let first: Promise<string | undefined>, second: Promise<string | undefined>, third: Promise<string | undefined>;
    act(() => { first = result.current.run(); second = result.current.run(); third = result.current.run(); });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(result.current.pending).toBe(true);
    await act(async () => { release(); await first; });
    expect(await first!).toBe('done');
    expect(await second!).toBeUndefined();
    expect(await third!).toBeUndefined();
    expect(result.current.pending).toBe(false);
  });
  it('allows another call after completion, and after a failure', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce('ok');
    const { result } = renderHook(() => useSingleFlight(fn));
    await act(async () => { await result.current.run().catch(() => undefined); });
    expect(result.current.pending).toBe(false);
    await act(async () => { await result.current.run(); });
    expect(fn).toHaveBeenCalledTimes(2);
  });
});

describe('useApi', () => {
  it('goes loading -> data', async () => {
    const { result } = renderHook(() => useApi('k', async () => 42));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe(42));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeUndefined();
  });
  it('surfaces errors and supports retry', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new ApiError('network', 0, 'x')).mockResolvedValueOnce('ok');
    const { result } = renderHook(() => useApi('k2', fn));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    expect(result.current.data).toBeUndefined();
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.data).toBe('ok'));
    expect(result.current.error).toBeUndefined();
  });
  it('keeps old data and flags it stale when a refresh fails', async () => {
    const fn = vi.fn().mockResolvedValueOnce('v1').mockRejectedValueOnce(new ApiError('network', 0, 'down'));
    const { result } = renderHook(() => useApi('k3', fn));
    await waitFor(() => expect(result.current.data).toBe('v1'));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.stale).toBe(true));
    expect(result.current.data).toBe('v1');
  });
  it('aborts the in-flight request when the key changes and ignores its result', async () => {
    const signals: AbortSignal[] = [];
    const fetcher = (s: AbortSignal) => { signals.push(s); return new Promise<string>((res) => setTimeout(() => res(`r${signals.length}`), 5)); };
    const { result, rerender } = renderHook(({ k }) => useApi(k, fetcher), { initialProps: { k: 'a' } });
    rerender({ k: 'b' });
    await waitFor(() => expect(result.current.data).toBe('r2'));
    expect(signals[0].aborted).toBe(true);
  });
  it('does nothing when key is null', () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useApi(null, fn));
    expect(fn).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});
