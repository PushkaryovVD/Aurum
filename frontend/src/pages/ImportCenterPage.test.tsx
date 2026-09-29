import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { IMPORT_OPTIONS } from "@/lib/importOptions";
import { ImportCenterPage } from "@/pages/ImportCenterPage";

describe("ImportCenterPage", () => {
  it("renders a link for every supported import option", () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    act(() => {
      root.render(
        <MemoryRouter>
          <ImportCenterPage />
        </MemoryRouter>
      );
    });

    for (const option of IMPORT_OPTIONS) {
      expect(container.innerHTML).toContain(`href="${option.to}"`);
    }

    act(() => root.unmount());
  });
});
