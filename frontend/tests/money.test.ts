import { describe, expect, it } from 'vitest';
import { formatMinor, minorToDecimalString, MoneyFormatError, parseMajorToMinor, safeFormatMinor } from '@/lib/money';

describe('parseMajorToMinor (typed amounts -> integer minor units, no floats)', () => {
  it('accepts grouped and decimal input', () => {
    expect(parseMajorToMinor('1,00,000', 'INR')).toBe(10_000_000);
    expect(parseMajorToMinor('12000.5', 'INR')).toBe(1_200_050);
    expect(parseMajorToMinor(' 0.07 ', 'USD')).toBe(7);
    expect(parseMajorToMinor('500', 'JPY')).toBe(500);
    expect(parseMajorToMinor('1.234', 'KWD')).toBe(1234);
    expect(parseMajorToMinor('0.1', 'USD')).toBe(10);
  });
  it('rejects more precision than the currency has, negatives and junk', () => {
    expect(parseMajorToMinor('1.005', 'INR')).toBeNull();
    expect(parseMajorToMinor('5.5', 'JPY')).toBeNull();
    expect(parseMajorToMinor('-5', 'INR')).toBeNull();
    expect(parseMajorToMinor('abc', 'INR')).toBeNull();
    expect(parseMajorToMinor('', 'INR')).toBeNull();
    expect(parseMajorToMinor('5', 'XXX')).toBeNull();
  });
});

describe('money adapter (integer minor units -> display)', () => {
  it('formats INR with Indian grouping and hides .00 on whole amounts', () => {
    expect(formatMinor(10_000_000, 'INR')).toBe('₹1,00,000');
    expect(formatMinor(500_000, 'INR')).toBe('₹5,000');
  });
  it('shows fraction digits when non-zero or when precise', () => {
    expect(formatMinor(42_500, 'INR')).toBe('₹425');
    expect(formatMinor(42_550, 'INR')).toBe('₹425.50');
    expect(formatMinor(42_500, 'INR', { precise: true })).toBe('₹425.00');
  });
  it('handles sign', () => {
    expect(formatMinor(-500_000, 'INR')).toBe('−₹5,000');
    expect(formatMinor(500_000, 'INR', { signed: true })).toBe('+₹5,000');
    expect(formatMinor(0, 'INR', { signed: true })).toBe('₹0');
  });
  it('respects per-currency exponents (JPY 0, KWD 3, USD 2)', () => {
    expect(minorToDecimalString(1234, 0)).toBe('1234');
    expect(minorToDecimalString(1234, 3)).toBe('1.234');
    expect(formatMinor(123_456, 'USD')).toBe('$1,234.56');
    expect(formatMinor(5_000, 'JPY')).toBe('¥5,000');
  });
  it('builds exact decimals without float division', () => {
    expect(minorToDecimalString(5, 2)).toBe('0.05');
    expect(minorToDecimalString(-5, 2)).toBe('-0.05');
    expect(minorToDecimalString(9_007_199_254_740_991, 2)).toBe('90071992547409.91');
  });
  it('rejects non-integers and unsupported currencies instead of guessing', () => {
    expect(() => formatMinor(10.5, 'INR')).toThrow(MoneyFormatError);
    expect(() => formatMinor(100, 'XXX')).toThrow(MoneyFormatError);
  });
  it('safeFormatMinor never throws', () => {
    expect(safeFormatMinor(null, 'INR')).toBe('—');
    expect(safeFormatMinor(undefined, 'INR')).toBe('—');
    expect(safeFormatMinor(1.5, 'INR')).toBe('—');
    expect(safeFormatMinor(100, 'XXX')).toBe('—');
  });
});
