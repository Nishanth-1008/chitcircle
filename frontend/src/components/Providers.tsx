'use client';
import type { ReactNode } from 'react';
import { SessionProvider } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';
import { ToastProvider } from '@/lib/toast';

export function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider><SessionProvider><ToastProvider>{children}</ToastProvider></SessionProvider></ThemeProvider>;
}
