import { describe, expect, it } from "vitest";
import { divideDecimal, multiplyDecimal } from "@/lib/decimal";

describe("exact decimal form previews", () => {
  it("multiplies without binary floating-point drift", () => {
    expect(multiplyDecimal("0.10", "3", 2)).toBe("0.30");
    expect(multiplyDecimal("12.34", "500.1234567890", 2)).toBe("6171.52");
  });

  it("computes a displayed transfer rate", () => {
    expect(divideDecimal("100", "50000", 6)).toBe("0.002");
  });
});
