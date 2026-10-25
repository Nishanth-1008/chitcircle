/**
 * Single currency / minor-unit adapter.
 *
 * The backend sends money as integer minor units (paise, cents...) plus a currency code. This module only
 * FORMATS those integers for display. It never computes contributions, dividends, commissions or payouts.
 * Exponents mirror backend `financial_engine/money.py` CURRENCY_EXPONENTS.
 */
export const CURRENCY_EXPONENTS: Record<string, number> = {
  INR: 2, USD: 2, EUR: 2, GBP: 2, AUD: 2, CAD: 2, SGD: 2, AED: 2, JPY: 0, KWD: 3,
};

export class MoneyFormatError extends Error {}

export interface FormatOptions {
  /** Prefix + for positive values (amount rows). Negative values always show −. */
  signed?: boolean;
  /** Always show the fraction digits (ledger / breakdown precision). Default hides ".00" on whole amounts. */
  precise?: boolean;
}

function localeFor(currency: string): string {
  return currency === 'INR' ? 'en-IN' : 'en-US';
}

/** Exact decimal string from integer minor units, without float division. */
export function minorToDecimalString(minor: number, exponent: number): string {
  if (!Number.isSafeInteger(minor)) throw new MoneyFormatError(`not an integer minor amount: ${minor}`);
  const negative = minor < 0;
  const digits = String(Math.abs(minor)).padStart(exponent + 1, '0');
  const whole = digits.slice(0, digits.length - exponent);
  const frac = exponent ? digits.slice(-exponent) : '';
  return `${negative ? '-' : ''}${whole}${frac ? '.' + frac : ''}`;
}

export function formatMinor(minor: number, currency: string, opts: FormatOptions = {}): string {
  const exponent = CURRENCY_EXPONENTS[currency];
  if (exponent === undefined) throw new MoneyFormatError(`unsupported currency: ${currency}`);
  const decimal = minorToDecimalString(minor, exponent);
  const isWhole = exponent === 0 || /^-?\d+\.0+$/.test(decimal);
  const showFraction = exponent > 0 && (opts.precise || !isWhole);
  const formatter = new Intl.NumberFormat(localeFor(currency), {
    style: 'currency',
    currency,
    minimumFractionDigits: showFraction ? exponent : 0,
    maximumFractionDigits: showFraction ? exponent : 0,
    currencyDisplay: 'symbol',
  });
  // Intl.NumberFormat accepts exact decimal strings (ES2023), so no float rounding is introduced.
  const absolute = formatter.format(decimal.replace('-', '') as unknown as number);
  if (minor < 0) return `−${absolute}`;
  return opts.signed && minor > 0 ? `+${absolute}` : absolute;
}

/** Never throws: falls back to an explicit placeholder so a bad payload cannot crash a screen. */
export function safeFormatMinor(minor: number | null | undefined, currency: string, opts?: FormatOptions): string {
  if (minor === null || minor === undefined) return '—';
  try {
    return formatMinor(minor, currency, opts);
  } catch {
    return '—';
  }
}
