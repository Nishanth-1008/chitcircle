'use client';
import { api } from './api/endpoints';
import { useApi } from './hooks';
import type { AppConfigView } from './types';

/** Server capabilities: whether sandbox confirmations are available and which payment gateway is active. */
export function useAppConfig(): AppConfigView | undefined {
  return useApi('app-config', (signal) => api.config({ token: null }, signal), { refetchOnFocus: false }).data;
}
