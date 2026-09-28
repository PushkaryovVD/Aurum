import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import type { Category, EnvelopeItem, EnvelopeMonth } from "@/types";
import { AvailableToAssignCard } from "./AvailableToAssignCard";
import { EnvelopeTable, orderEnvelopeItems } from "./EnvelopeTable";
import { EnvelopeWarnings } from "./EnvelopeWarnings";

const item: EnvelopeItem = {
  category_id: 4,
  category_name: "Groceries",
  category_color: "#22c55e",
  category_icon: "shopping-cart",
  is_unbudgeted: false,
  planned_amount: "500.00",
  assigned_amount: "100.00",
  activity: "-50.00",
  carried_in: "0.00",
  available: "50.00",
  is_overspent: false,
  rollover_positive: true,
  rollover_negative: true,
  has_row: true,
};

const month: EnvelopeMonth = {
  year: 2026,
  month: 8,
  tracking_start: { year: 2026, month: 8 },
  is_closed: false,
  has_ledger_drift: false,
  fx_incomplete: false,
  income: "1000.00",
  assigned: "600.00",
  available_to_assign: "400.00",
  items: [item],
  warnings: [],
};

function renderHtml(node: ReactNode): string {
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() => root.render(node));
  const html = container.innerHTML;
  act(() => root.unmount());
  return html;
}

afterEach(() => setLanguage("ru"));

describe("envelope status components", () => {
  it("reuses the category hierarchy order and marks child depth", () => {
    const child = { ...item, category_id: 5, category_name: "Fruit" };
    const categories: Category[] = [
      { id: 5, name: "Fruit", kind: "expense", icon: null, color: "#111111", sort_order: 0, is_default: false, parent_id: 4 },
      { id: 4, name: "Groceries", kind: "expense", icon: null, color: "#222222", sort_order: 1, is_default: false, parent_id: null },
    ];
    expect(orderEnvelopeItems([child, item], categories)).toEqual([
      { item, depth: 0 },
      { item: child, depth: 1 },
    ]);
  });

  it("renders cumulative available-to-assign separately from income and assigned", () => {
    setLanguage("en");
    const html = renderHtml(<AvailableToAssignCard month={month} />);
    expect(html).toContain("Available to assign");
    expect(html).toContain("Income this month");
    expect(html).toContain("Assigned this month");
  });

  it("renders underfunded only when the server supplies the warning", () => {
    setLanguage("en");
    const withoutServerWarning = renderHtml(<EnvelopeWarnings warnings={[]} />);
    const withServerWarning = renderHtml(
      <EnvelopeWarnings warnings={[{ code: "underfunded", category_id: 4, amount: "400.00" }]} />
    );
    expect(withoutServerWarning).not.toContain("underfunded");
    expect(withServerWarning).toContain("underfunded");
  });

  it("disables envelope planning actions for a closed month", () => {
    setLanguage("en");
    const html = renderHtml(
      <EnvelopeTable items={[item]} isClosed onAssign={() => undefined} onMove={() => undefined} />
    );
    expect(html).toContain("This month is closed");
    expect(html).toMatch(/<button[^>]*disabled/);
  });
});
