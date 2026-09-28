import { describe, expect, it } from "vitest";
import { allocationLimit, envelopeErrorKey, envelopeProgressPercent, moveValidationKey } from "./envelopeFormLogic";

describe("allocationLimit", () => {
  it("adds the current assignment to available-to-assign without float rounding", () => {
    expect(allocationLimit("0.10", "0.20")).toBe("0.30");
  });

  it("clamps a requested assignment to the exact available limit", () => {
    expect(allocationLimit("25.00", "10.00", "40.00")).toBe("35.00");
  });
});

describe("moveValidationKey", () => {
  it("rejects moves above the source assigned amount", () => {
    expect(moveValidationKey("20.01", "20.00", 1, 2)).toBe("envelope.move.tooMuch");
  });

  it("rejects the same source and destination", () => {
    expect(moveValidationKey("1.00", "20.00", 1, 1)).toBe("envelope.move.sameCategory");
  });
});

describe("envelopeErrorKey", () => {
  it("maps closed-month and available-to-assign server errors to translated keys", () => {
    expect(envelopeErrorKey({ status: 409, message: "Envelope month 2026-08 is closed" })).toBe("envelope.error.closed");
    expect(envelopeErrorKey({ status: 400, message: "Allocation exceeds money available to assign" })).toBe("envelope.error.available");
  });
});

describe("envelopeProgressPercent", () => {
  it("uses exact decimal cents and clamps progress to the visible range", () => {
    expect(envelopeProgressPercent("33.33", "100.00")).toBe(33);
    expect(envelopeProgressPercent("125.00", "100.00")).toBe(100);
    expect(envelopeProgressPercent("-1.00", "100.00")).toBe(0);
  });
});
