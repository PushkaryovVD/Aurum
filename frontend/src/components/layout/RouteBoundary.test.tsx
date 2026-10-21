import { act, lazy } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { setLanguage } from "@/lib/i18n";
import { RouteBoundary } from "./RouteBoundary";

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
  vi.restoreAllMocks();
});

it("shows a loading status while a route chunk is pending", () => {
  setLanguage("en");
  const Pending = lazy(() => new Promise<never>(() => {}));
  const view = render(<RouteBoundary><Pending /></RouteBoundary>);
  expect(view.querySelector('[role="status"]')?.textContent).toBe("Loading…");
});

it("shows a reload prompt instead of a blank page when a chunk fails to load", async () => {
  setLanguage("en");
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Broken = lazy(() => Promise.reject(new Error("chunk failed")));
  const view = render(<RouteBoundary><Broken /></RouteBoundary>);
  await act(async () => {
    await Promise.resolve();
  });
  expect(view.querySelector('[role="alert"]')?.textContent).toContain("Could not load this section");
  expect(view.querySelector("button")?.textContent).toBe("Reload page");
});
