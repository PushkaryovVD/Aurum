import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import { SpendingByCategoryCard } from "./SpendingByCategoryCard";
import { TotalBalanceCard } from "./TotalBalanceCard";

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

it("renders an unavailable balance as unknown instead of zero", () => {
  setLanguage("en");
  const view = render(<TotalBalanceCard state="unavailable" />);
  const headline = view.querySelector(".tabular-nums");

  expect(headline?.textContent).toBe("—");
  expect(headline?.textContent).not.toContain("0");
});

it("does not present a failed category request as an empty month", () => {
  setLanguage("en");
  const view = render(<SpendingByCategoryCard state="unavailable" />);

  expect(view.textContent).toContain("Data is currently unavailable");
  expect(view.textContent).not.toContain("No expenses yet this month");
});

