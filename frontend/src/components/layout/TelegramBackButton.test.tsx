import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { TelegramBackButton } from "./TelegramBackButton";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let container: HTMLDivElement | null = null;
let go: ReturnType<typeof useNavigate> | null = null;

function Probe() {
  go = useNavigate();
  return null;
}

function backButton() {
  let handler: (() => void) | null = null;
  return {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn((next: () => void) => { handler = next; }),
    offClick: vi.fn(),
    press: () => handler?.(),
  };
}

function render(path: string) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  act(() => root?.render(<MemoryRouter initialEntries={[path]}><TelegramBackButton /><Probe /></MemoryRouter>));
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  go = null;
  delete window.Telegram;
});

it("hides the back button on top-level screens", () => {
  const button = backButton();
  window.Telegram = { WebApp: { initData: "test-only", BackButton: button } };
  render("/");
  expect(button.hide).toHaveBeenCalled();
  expect(button.show).not.toHaveBeenCalled();
});

it("shows it on inner screens and returns to the dashboard when opened directly", () => {
  const button = backButton();
  window.Telegram = { WebApp: { initData: "test-only", BackButton: button } };
  render("/budget");
  expect(button.show).toHaveBeenCalled();
  act(() => button.press());
  expect(button.hide).toHaveBeenCalled();
});

it("goes back through in-app history", () => {
  const button = backButton();
  window.Telegram = { WebApp: { initData: "test-only", BackButton: button } };
  render("/");
  act(() => go!("/transactions"));
  act(() => go!("/budget"));
  act(() => button.press());
  // Back from /budget lands on /transactions, which still shows the button.
  expect(button.onClick).toHaveBeenCalledTimes(3);
  expect(button.offClick).toHaveBeenCalled();
});

it("does nothing outside Telegram", () => {
  const button = backButton();
  window.Telegram = { WebApp: { initData: "", BackButton: button } };
  render("/budget");
  expect(button.show).not.toHaveBeenCalled();
});
