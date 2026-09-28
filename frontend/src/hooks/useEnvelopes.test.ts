import { describe, expect, it } from "vitest";
import { envelopeInvalidationKeys, previousMonth } from "./useEnvelopes";

describe("envelope query invalidation", () => {
  it("crosses the year boundary when selecting the previous month", () => {
    expect(previousMonth(2026, 1)).toEqual({ year: 2025, month: 12 });
  });

  it("invalidates envelope lists, the edited month, its previous month, and alerts", () => {
    expect(envelopeInvalidationKeys(2026, 1)).toEqual([
      ["envelopes"],
      ["envelope-month", 2026, 1],
      ["envelope-month", 2025, 12],
      ["financial-alerts"],
    ]);
  });
});
