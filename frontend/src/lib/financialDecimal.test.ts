import { describe, expect, it } from "vitest";
import {
  addDecimals,
  canonicalDecimal,
  compareDecimals,
  decimalPlaces,
  divideDecimals,
  formatDecimal,
  multiplyDecimals,
  powDecimal,
  sumDecimals,
  validateDecimalScale,
} from "@/lib/financialDecimal";

describe("financialDecimal", () => {
  it("parses strictly and serializes without exponent or insignificant zeroes", () => {
    expect(canonicalDecimal("  -00123.4500 ")).toBe("-123.45");
    expect(canonicalDecimal("0,000001", { allowComma: true })).toBe("0.000001");
    expect(canonicalDecimal("-0.000")).toBe("0");
    expect(() => canonicalDecimal("1e-7")).toThrow();
    expect(() => canonicalDecimal("NaN")).toThrow();
    expect(() => canonicalDecimal("1,2")).toThrow();
  });

  it("compares, sums and computes without IEEE-754 drift", () => {
    expect(compareDecimals("9007199254740993", "9007199254740992")).toBe(1);
    expect(compareDecimals("0.000000000000000001", "0")).toBe(1);
    expect(addDecimals("0.1", "0.2")).toBe("0.3");
    expect(sumDecimals(["9007199254740993", "0.000001", "-0.000001"])).toBe("9007199254740993");
    expect(multiplyDecimals("12.34", "500.123456789", 2)).toBe("6171.52");
    expect(divideDecimals("1", "3", 18)).toBe("0.333333333333333333");
    expect(powDecimal("1.1", 3)).toBe("1.331");
  });

  it("uses half-even rounding and validates field scales", () => {
    expect(multiplyDecimals("1.005", "1", 2)).toBe("1");
    expect(multiplyDecimals("1.015", "1", 2)).toBe("1.02");
    expect(decimalPlaces("1.2300")).toBe(4);
    expect(validateDecimalScale("1.000001", 6)).toBe(true);
    expect(validateDecimalScale("1.0000001", 6)).toBe(false);
  });

  it("formats large and tiny values without converting through Number", () => {
    expect(formatDecimal("9007199254740993.12", { locale: "en-US", maximumFractionDigits: 2 })).toBe(
      "9,007,199,254,740,993.12",
    );
    expect(formatDecimal("0.000000000000000001", { locale: "en-US", maximumFractionDigits: 18 })).toBe(
      "0.000000000000000001",
    );
  });
});
