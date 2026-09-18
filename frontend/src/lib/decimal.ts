/** Exact decimal helpers for form previews. Financial arithmetic must not
 * pass through IEEE-754 Number before it is rounded for display. */
function parts(value: string): { units: bigint; scale: number } | null {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  return { units: BigInt(`${whole}${fraction}`), scale: fraction.length };
}

function roundedDivide(numerator: bigint, denominator: bigint): bigint {
  const quotient = numerator / denominator;
  const remainder = numerator % denominator;
  return remainder * 2n >= denominator ? quotient + 1n : quotient;
}

function render(units: bigint, scale: number): string {
  if (scale === 0) return units.toString();
  const padded = units.toString().padStart(scale + 1, "0");
  return `${padded.slice(0, -scale)}.${padded.slice(-scale)}`;
}

export function multiplyDecimal(left: string, right: string, fractionDigits = 2): string | null {
  const a = parts(left); const b = parts(right);
  if (!a || !b) return null;
  const sourceScale = a.scale + b.scale;
  const product = a.units * b.units;
  const shift = sourceScale - fractionDigits;
  const units = shift > 0
    ? roundedDivide(product, 10n ** BigInt(shift))
    : product * 10n ** BigInt(-shift);
  return render(units, fractionDigits);
}

export function divideDecimal(numerator: string, denominator: string, fractionDigits = 6): string | null {
  const a = parts(numerator); const b = parts(denominator);
  if (!a || !b || b.units === 0n) return null;
  const scaledNumerator = a.units * 10n ** BigInt(b.scale + fractionDigits);
  const scaledDenominator = b.units * 10n ** BigInt(a.scale);
  return render(roundedDivide(scaledNumerator, scaledDenominator), fractionDigits).replace(/\.?0+$/, "");
}
