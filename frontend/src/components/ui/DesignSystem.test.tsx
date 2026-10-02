/// <reference types="node" />

import { act } from "react";
import { createRoot } from "react-dom/client";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Page, PageHeader } from "@/components/ui/Page";


function render(node: React.ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return {
    container,
    unmount() {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("design system primitives", () => {
  it("defines semantic layout, type, radius, elevation, and focus tokens for both appearances", () => {
    const designSystemCss = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

    for (const token of ["--font-size-page-title", "--space-page-inline", "--radius-card", "--shadow-card", "--focus"]) {
      expect(designSystemCss).toContain(token);
    }
    expect(designSystemCss.match(/--focus:/g)).toHaveLength(3);
  });

  it("provides a semantic page header and labelled card composition", () => {
    const view = render(
      <Page>
        <PageHeader title="Overview" description="Your monthly position" actions={<Button>Change period</Button>} />
        <Card aria-labelledby="summary-title">
          <CardHeader>
            <CardTitle id="summary-title">Summary</CardTitle>
          </CardHeader>
          <CardContent>Details</CardContent>
        </Card>
      </Page>
    );

    expect(view.container.querySelector('[data-slot="page"]')?.className).toContain("min-w-0");
    expect(view.container.querySelector("header h1")?.textContent).toBe("Overview");
    expect(view.container.querySelector("header p")?.textContent).toBe("Your monthly position");
    expect(view.container.querySelector('[aria-labelledby="summary-title"]')).not.toBeNull();
    view.unmount();
  });

  it("gives interactive controls a visible focus treatment and touch-sized target", () => {
    const view = render(<Button>Continue</Button>);
    const button = view.container.querySelector("button");

    expect(button?.className).toContain("min-h-11");
    expect(button?.className).toContain("focus-visible:ring-2");
    view.unmount();
  });
});

describe("responsive navigation", () => {
  it("connects the mobile menu trigger to its expanded navigation dialog", () => {
    const view = render(
      <MemoryRouter>
        <Topbar mobileNavOpen onOpenMobileNav={() => undefined} />
      </MemoryRouter>
    );

    const trigger = view.container.querySelector("header button");
    expect(trigger?.getAttribute("aria-controls")).toBe("mobile-navigation");
    expect(trigger?.getAttribute("aria-expanded")).toBe("true");
    view.unmount();
  });

  it("exposes the mobile drawer as a labelled modal and focuses its close control", () => {
    const onClose = vi.fn();
    const view = render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapsed={() => undefined} mobileOpen onCloseMobile={onClose} />
      </MemoryRouter>
    );

    const dialog = view.container.querySelector('[role="dialog"]');
    const close = dialog?.querySelector("button");
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
    expect(dialog?.getAttribute("aria-label")).toBeTruthy();
    expect(dialog?.id).toBe("mobile-navigation");
    expect(close).toBe(document.activeElement);
    expect(close?.className).toContain("min-h-11");

    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(onClose).toHaveBeenCalledOnce();
    view.unmount();
  });
});
