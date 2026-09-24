// @vitest-environment jsdom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setLanguage } from "@/lib/i18n";
import type { Asset } from "@/types";
import { AssetFormModal, validateAssetForm } from "./AssetFormModal";
import { AssetsTable } from "./AssetsTable";
import { AssetRevaluationReminderCard } from "@/pages/NetWorthPage";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const asset: Asset = {
  id: 1,
  name: "Vehicle",
  asset_class: "vehicles",
  currency: "KZT",
  notes: null,
  capital_role: "neutral",
  monthly_cash_flow: null,
  risk_level: "medium",
  acquisition_date: "2024-01-01",
  acquisition_cost: "1000.00",
  residual_value: "100.00",
  valuation_mode: "straight_line",
  useful_life_years: 5,
  annual_depreciation_rate: null,
  current_value: "900.00",
  current_base_value_kzt: "900.00",
  as_of_date: "2025-01-01",
  exchange_rate_to_kzt: "1",
  projected_value: "800.00",
  accumulated_depreciation: "200.00",
  latest_market_value: "900.00",
  latest_market_value_date: "2025-01-01",
  unrealized_change: "-100.00",
};

let root: ReturnType<typeof createRoot> | null = null;
let container: HTMLDivElement | null = null;

function render(node: React.ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  act(() => root?.render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  container = null;
  setLanguage("ru");
});

describe("asset depreciation UI", () => {
  it.each([
    ["ru", "Рыночная оценка", "Расчётная стоимость"],
    ["en", "Market valuation", "Projected value"],
  ] as const)("renders recorded and projected values distinctly in %s", (language, marketLabel, projectionLabel) => {
    setLanguage(language);
    const view = render(<AssetsTable items={[asset]} onEdit={() => undefined} onDelete={() => undefined} />);
    expect(view.textContent).toContain(marketLabel);
    expect(view.textContent).toContain(projectionLabel);
  });

  it("uses mobile-first form grids and decimal text inputs", () => {
    const view = render(<AssetFormModal open onClose={() => undefined} asset={asset} />);
    const grids = [...view.querySelectorAll(".grid")];
    expect(grids.some((element) => element.className.includes("grid-cols-1") && element.className.includes("sm:grid-cols-2"))).toBe(true);
    const valueInput = view.querySelector<HTMLInputElement>("#asset-value");
    expect(valueInput?.type).toBe("text");
    expect(valueInput?.inputMode).toBe("decimal");
  });

  it("offers responsive accept and manual-market actions", () => {
    setLanguage("en");
    const onAccept = vi.fn();
    const onEnterMarketValue = vi.fn();
    const view = render(
      <AssetRevaluationReminderCard
        reminder={{
          asset_id: asset.id,
          asset_name: asset.name,
          due_date: "2025-04-01",
          projected_value: "800.00",
          latest_market_value: "900.00",
          latest_market_value_date: "2025-01-01",
        }}
        asset={asset}
        isPending={false}
        onAccept={onAccept}
        onEnterMarketValue={onEnterMarketValue}
      />,
    );
    const card = view.firstElementChild;
    expect(card?.className).toContain("flex-col");
    expect(card?.className).toContain("sm:flex-row");
    const buttons = [...view.querySelectorAll("button")];
    expect(buttons.every((button) => button.className.includes("w-full") && button.className.includes("sm:w-auto"))).toBe(true);
    act(() => buttons[0]?.click());
    act(() => buttons[1]?.click());
    expect(onEnterMarketValue).toHaveBeenCalledWith(asset);
    expect(onAccept).toHaveBeenCalledWith(asset.id);
  });

  it("validates decimal strings and depreciation cross-field rules", () => {
    const base = {
      name: "Vehicle",
      asset_class: "vehicles" as const,
      value: "900.00",
      as_of_date: "2025-01-01",
      notes: "",
      capital_role: "neutral" as const,
      monthly_cash_flow: "",
      risk_level: "medium" as const,
      acquisition_date: "2024-01-01",
      acquisition_cost: "1000.00",
      residual_value: "100.00",
      valuation_mode: "straight_line" as const,
      useful_life_years: "5",
      annual_depreciation_rate: "",
    };
    expect(validateAssetForm(base)).toBeNull();
    expect(validateAssetForm({ ...base, value: "900,00" })).toBe("netWorth.form.validation.money");
    expect(validateAssetForm({ ...base, residual_value: "1001.00" })).toBe("netWorth.form.validation.residualValue");
    expect(validateAssetForm({ ...base, useful_life_years: "0" })).toBe("netWorth.form.validation.usefulLife");
  });
});
