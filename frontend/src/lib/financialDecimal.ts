import Decimal from "decimal.js";

const FinancialDecimal = Decimal.clone({
  precision: 60,
  rounding: Decimal.ROUND_HALF_EVEN,
  toExpNeg: -1_000_000_000,
  toExpPos: 1_000_000_000,
});

const DOT_DECIMAL_PATTERN = /^-?\d+(?:\.\d+)?$/;
const COMMA_DECIMAL_PATTERN = /^-?\d+(?:[.,]\d+)?$/;

export interface DecimalParseOptions {
  allowComma?: boolean;
}

export interface DecimalFormatOptions {
  locale?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  useGrouping?: boolean;
}

function normalizedInput(value: string, options: DecimalParseOptions = {}): string {
  if (typeof value !== "string") {
    throw new TypeError("financial values must be decimal strings");
  }

  const trimmed = value.trim();
  const pattern = options.allowComma ? COMMA_DECIMAL_PATTERN : DOT_DECIMAL_PATTERN;
  if (!pattern.test(trimmed)) {
    throw new RangeError("financial values must use plain decimal notation");
  }

  return options.allowComma ? trimmed.replace(",", ".") : trimmed;
}

function parseDecimal(value: string, options?: DecimalParseOptions): Decimal {
  return new FinancialDecimal(normalizedInput(value, options));
}

function serialize(value: Decimal): string {
  if (!value.isFinite()) {
    throw new RangeError("financial values must be finite");
  }
  return value.isZero() ? "0" : value.toFixed();
}

function requireScale(scale: number): void {
  if (!Number.isSafeInteger(scale) || scale < 0) {
    throw new RangeError("decimal scale must be a non-negative safe integer");
  }
}

function rounded(value: Decimal, scale: number): Decimal {
  requireScale(scale);
  return value.toDecimalPlaces(scale, Decimal.ROUND_HALF_EVEN);
}

export function canonicalDecimal(value: string, options?: DecimalParseOptions): string {
  return serialize(parseDecimal(value, options));
}

export function compareDecimals(left: string, right: string): number {
  return parseDecimal(left).comparedTo(parseDecimal(right));
}

export function addDecimals(left: string, right: string): string {
  return serialize(parseDecimal(left).plus(parseDecimal(right)));
}

export function sumDecimals(values: readonly string[]): string {
  const total = values.reduce<Decimal>((sum, value) => sum.plus(parseDecimal(value)), new FinancialDecimal(0));
  return serialize(total);
}

export function multiplyDecimals(left: string, right: string, scale?: number): string {
  const product = parseDecimal(left).times(parseDecimal(right));
  return serialize(scale === undefined ? product : rounded(product, scale));
}

export function divideDecimals(numerator: string, denominator: string, scale?: number): string {
  const divisor = parseDecimal(denominator);
  if (divisor.isZero()) {
    throw new RangeError("cannot divide by zero");
  }

  const quotient = parseDecimal(numerator).dividedBy(divisor);
  return serialize(scale === undefined ? quotient : rounded(quotient, scale));
}

export function powDecimal(value: string, exponent: number): string {
  if (!Number.isSafeInteger(exponent)) {
    throw new RangeError("decimal exponent must be a safe integer");
  }
  return serialize(parseDecimal(value).toPower(exponent));
}

export function decimalPlaces(value: string, options?: DecimalParseOptions): number {
  const normalized = normalizedInput(value, options);
  const point = normalized.indexOf(".");
  return point === -1 ? 0 : normalized.length - point - 1;
}

export function validateDecimalScale(value: string, maximumScale: number, options?: DecimalParseOptions): boolean {
  requireScale(maximumScale);
  try {
    return decimalPlaces(value, options) <= maximumScale;
  } catch {
    return false;
  }
}

function localizedSymbols(locale: string): { decimal: string; minus: string; digits: readonly string[] } {
  const symbolFormatter = new Intl.NumberFormat(locale, { useGrouping: false });
  const decimal = symbolFormatter.formatToParts(1.1).find((part) => part.type === "decimal")?.value ?? ".";
  const minus = symbolFormatter.formatToParts(-1).find((part) => part.type === "minusSign")?.value ?? "-";
  const digits = Array.from({ length: 10 }, (_, digit) => symbolFormatter.format(BigInt(digit)));
  return { decimal, minus, digits };
}

function localizeDigits(value: string, digits: readonly string[]): string {
  return value.replace(/\d/g, (digit) => digits[Number(digit)] ?? digit);
}

export function formatDecimal(value: string, options: DecimalFormatOptions = {}): string {
  const parsed = parseDecimal(value);
  const sourceScale = decimalPlaces(value);
  const maximumFractionDigits = options.maximumFractionDigits ?? sourceScale;
  const minimumFractionDigits = options.minimumFractionDigits ?? 0;
  requireScale(maximumFractionDigits);
  requireScale(minimumFractionDigits);
  if (minimumFractionDigits > maximumFractionDigits) {
    throw new RangeError("minimumFractionDigits cannot exceed maximumFractionDigits");
  }

  const result = rounded(parsed, maximumFractionDigits);
  const fixed = result.abs().toFixed(maximumFractionDigits);
  const [whole, paddedFraction = ""] = fixed.split(".");
  let fraction = paddedFraction;
  while (fraction.length > minimumFractionDigits && fraction.endsWith("0")) {
    fraction = fraction.slice(0, -1);
  }

  const locale = options.locale ?? undefined;
  const integerFormatter = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
    useGrouping: options.useGrouping ?? true,
  });
  const symbols = localizedSymbols(integerFormatter.resolvedOptions().locale);
  const localizedWhole = integerFormatter.format(BigInt(whole));
  const localizedFraction = fraction === "" ? "" : `${symbols.decimal}${localizeDigits(fraction, symbols.digits)}`;
  const sign = result.isNegative() && !result.isZero() ? symbols.minus : "";
  return `${sign}${localizedWhole}${localizedFraction}`;
}
