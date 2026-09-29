import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import { BudgetPage } from "@/pages/BudgetPage";
import { CategorizationRulesPage } from "@/pages/CategorizationRulesPage";
import { EnvelopePage } from "@/pages/EnvelopePage";
import { StatementImportPage } from "@/pages/StatementImportPage";

function renderPage(node: React.ReactNode) {
  const container = document.createElement("div");
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
  act(() => {
    root.render(
      <MemoryRouter>
        <QueryClientProvider client={client}>{node}</QueryClientProvider>
      </MemoryRouter>
    );
  });
  return { container, root };
}

afterEach(() => setLanguage("ru"));

describe("contextual help integration", () => {
  it.each([
    ["budgets", <BudgetPage />],
    ["envelopes", <EnvelopePage />],
    ["categorization rules", <CategorizationRulesPage />],
    ["statement import", <StatementImportPage />],
  ])("adds the shared disclosure to %s", (_name, page) => {
    setLanguage("en");
    const view = renderPage(page);
    const helpButton = Array.from(view.container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("How this works")
    );

    expect(helpButton).toBeDefined();
    expect(helpButton?.getAttribute("aria-expanded")).toBe("false");

    act(() => view.root.unmount());
  });
});
