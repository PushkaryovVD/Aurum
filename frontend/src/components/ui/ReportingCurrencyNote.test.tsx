import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import { formatReportingAmount, formatSignedReportingAmount } from "@/lib/format";
import { BudgetList } from "@/components/budget/BudgetList";
import { ReportingCurrencyNote } from "./ReportingCurrencyNote";
import type { BudgetStatus } from "@/types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let container: HTMLDivElement | null = null;

function render(node: React.ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root?.render(node));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  container = null;
  setLanguage("ru");
});

describe("formatReportingAmount", () => {
  it("formats in the currency the response names, not the settings default", () => {
    setLanguage("en");
    expect(formatReportingAmount("6000.00", "USD")).toBe("$6,000");
    expect(formatSignedReportingAmount("5900", "USD")).toBe("+$5,900");
  });

  it("renders an unconvertible amount as unknown, never as zero", () => {
    expect(formatReportingAmount(null, "USD")).toBe("—");
    expect(formatSignedReportingAmount(null, "USD")).toBe("—");
  });
});

describe("ReportingCurrencyNote", () => {
  it("stays silent for a complete KZT answer", () => {
    const view = render(<ReportingCurrencyNote currency="KZT" />);
    expect(view.textContent).toBe("");
  });

  it("explains the conversion and flags missing rates", () => {
    setLanguage("en");
    const converted = render(<ReportingCurrencyNote currency="USD" />);
    expect(converted.textContent).toContain("converted from tenge to USD");
    act(() => root?.render(<ReportingCurrencyNote currency="USD" incomplete />));
    expect(converted.textContent).toContain("could not be converted to USD");
  });
});

describe("BudgetList", () => {
  const item: BudgetStatus = {
    budget_id: 1,
    category_id: 2,
    category_name: "Groceries",
    category_color: "#1baf7a",
    category_icon: null,
    monthly_limit: "800.00",
    spent: null,
    remaining: null,
    percent: null,
    is_over_budget: false,
  };

  it("shows an unconvertible spend as unknown instead of a false 0%", () => {
    setLanguage("en");
    const view = render(<BudgetList items={[item]} currency="USD" onEdit={() => {}} onDelete={() => {}} />);
    expect(view.textContent).toContain("— / $800");
    expect(view.textContent).not.toContain("0%");
  });

  it("labels spend and limit with the response currency", () => {
    setLanguage("en");
    const view = render(
      <BudgetList
        items={[{ ...item, spent: "1000.00", remaining: "-200.00", percent: 125, is_over_budget: true }]}
        currency="USD"
        onEdit={() => {}}
        onDelete={() => {}}
      />
    );
    expect(view.textContent).toContain("$1,000 / $800");
    expect(view.textContent).toContain("125%");
  });
});
