'use client';
import type { ReactNode } from 'react';
import { SessionProvider } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';

export function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider><SessionProvider>{children}</SessionProvider></ThemeProvider>;
}
