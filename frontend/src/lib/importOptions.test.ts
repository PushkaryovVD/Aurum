import { describe, expect, it } from "vitest";
import { NAV_ITEMS } from "@/lib/navigation";
import { IMPORT_OPTIONS } from "@/lib/importOptions";

describe("transaction import entry points", () => {
  it("does not expose cryptocurrency in the primary navigation", () => {
    expect(NAV_ITEMS.some((item) => item.to === "/crypto")).toBe(false);
  });

  it("offers the supported bank-statement formats and generic CSV import", () => {
    expect(IMPORT_OPTIONS).toEqual([
      expect.objectContaining({
        id: "kaspi",
        to: "/transactions/import/statements?bank=kaspi",
        accept: ".pdf,application/pdf",
      }),
      expect.objectContaining({
        id: "freedom-bank",
        to: "/transactions/import/statements?bank=freedom-bank",
        accept: ".pdf,application/pdf",
      }),
      expect.objectContaining({
        id: "tradernet",
        to: "/transactions/import/statements?bank=tradernet",
        accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      expect.objectContaining({ id: "csv", to: "/transactions/import/csv", accept: ".csv,text/csv" }),
    ]);
  });
});
