import { DEFAULT_CURRENCY } from '../config';
import type { LedgerEventView, SettlementView } from '../types';

export interface ResolvedCurrency {
  code: string;
  /** true when no API payload carried a currency and the configured default is being used */
  assumed: boolean;
}

/**
 * GET /cycles/{id} and GET /circles/{id} do not return a currency code. Prefer one carried by the settlement or
 * ledger payload of the same round; only then fall back to the configured default and mark it as assumed.
 */
export function resolveCurrency(source?: { settlement?: SettlementView; ledger?: LedgerEventView[] }): ResolvedCurrency {
  const fromSettlement = source?.settlement?.settlement.currency;
  if (fromSettlement) return { code: fromSettlement, assumed: false };
  const fromLedger = source?.ledger?.find((e) => e.currency)?.currency;
  if (fromLedger) return { code: fromLedger, assumed: false };
  return { code: DEFAULT_CURRENCY, assumed: true };
}
