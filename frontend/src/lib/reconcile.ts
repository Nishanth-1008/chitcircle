/** Plain-language labels for backend reconciliation codes. Unknown codes are shown humanized, never hidden. */
import { humanize } from './status';

const LABELS: Record<string, string> = {
  UNDERPAID: 'Paid less than the amount due',
  OVERPAID: 'Paid more than the amount due',
  INTERNAL_PROVIDER_MISMATCH: 'Our records and the provider’s records differ',
  DUPLICATE_PROVIDER_TXN: 'Duplicate provider transaction',
  CURRENCY_MISMATCH: 'Currency does not match',
  PAYOUT_NOT_COMPLETED: 'Payout was not completed by the provider',
  PAYOUT_AMOUNT_MISMATCH: 'Payout amount differs from the settlement',
  LEDGER_OBLIGATION_MISMATCH: 'Ledger and member obligation disagree',
  UNBALANCED_JOURNAL: 'A ledger journal does not balance',
  POOL_NOT_ZERO: 'The circle pool does not net to zero',
};

export const reconcileLabel = (code: string) => LABELS[code] ?? humanize(code);
