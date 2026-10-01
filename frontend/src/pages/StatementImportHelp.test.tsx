import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import { StatementImportPage } from "@/pages/StatementImportPage";

afterEach(() => setLanguage("ru"));

describe("StatementImportPage help", () => {
  it("shows workflow-specific review guidance", () => {
    setLanguage("en");
    const container = document.createElement("div");
    const root = createRoot(container);
    const client = new QueryClient({
      defaultOptions: { queries: { enabled: false, retry: false } },
    });

    act(() => {
      root.render(
        <MemoryRouter>
          <QueryClientProvider client={client}>
            <StatementImportPage />
          </QueryClientProvider>
        </MemoryRouter>
      );
    });

    const helpButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("How this works")
    );
    expect(helpButton).toBeDefined();

    act(() => helpButton?.click());

    expect(container.textContent).toContain("review every recognized row");
    expect(container.textContent).toContain("Nothing reaches the ledger until you press Import");

    act(() => root.unmount());
  });
});
