import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Handler = () => void;

function fakeWebApp(overrides: Record<string, unknown> = {}) {
  const handlers = new Map<string, Handler>();
  return {
    initData: "query_id=test-only",
    platform: "ios",
    version: "8.0",
    isFullscreen: false,
    isVersionAtLeast: (version: string) => Number(version) <= 8.0,
    ready: vi.fn(),
    expand: vi.fn(),
    requestFullscreen: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    setHeaderColor: vi.fn(),
    setBackgroundColor: vi.fn(),
    setBottomBarColor: vi.fn(),
    onEvent: vi.fn((event: string, handler: Handler) => handlers.set(event, handler)),
    offEvent: vi.fn(),
    handlers,
    ...overrides,
  };
}

let meta: HTMLMetaElement;

beforeEach(() => {
  // Fresh module state (the shell initializes once per page load).
  vi.resetModules();
  document.documentElement.className = "";
  meta = document.createElement("meta");
  meta.name = "theme-color";
  meta.content = "#0d0d0d";
  document.head.append(meta);
});

afterEach(() => {
  meta.remove();
  delete window.Telegram;
});

describe("initTelegramShell", () => {
  it("does nothing in an ordinary browser", async () => {
    window.Telegram = { WebApp: fakeWebApp({ initData: "" }) };
    const { initTelegramShell } = await import("./telegram");
    expect(initTelegramShell()).toBe(false);
    expect(window.Telegram.WebApp!.requestFullscreen).not.toHaveBeenCalled();
    expect(document.documentElement.classList.contains("tg-app")).toBe(false);
  });

  it("goes full screen on a phone, blocks swipe-to-close and paints Telegram chrome", async () => {
    const webApp = fakeWebApp();
    window.Telegram = { WebApp: webApp };
    const { initTelegramShell } = await import("./telegram");
    expect(initTelegramShell()).toBe(true);
    expect(webApp.ready).toHaveBeenCalled();
    expect(webApp.requestFullscreen).toHaveBeenCalled();
    expect(webApp.disableVerticalSwipes).toHaveBeenCalled();
    expect(webApp.setHeaderColor).toHaveBeenCalledWith("#0d0d0d");
    expect(webApp.setBackgroundColor).toHaveBeenCalledWith("#0d0d0d");
    expect(webApp.setBottomBarColor).toHaveBeenCalledWith("#0d0d0d");
    expect(document.documentElement.classList.contains("tg-app")).toBe(true);

    webApp.isFullscreen = true;
    webApp.handlers.get("fullscreenChanged")!();
    expect(document.documentElement.classList.contains("tg-fullscreen")).toBe(true);
  });

  it("keeps desktop Telegram in the regular panel", async () => {
    const webApp = fakeWebApp({ platform: "tdesktop" });
    window.Telegram = { WebApp: webApp };
    const { initTelegramShell } = await import("./telegram");
    initTelegramShell();
    expect(webApp.requestFullscreen).not.toHaveBeenCalled();
    expect(webApp.expand).toHaveBeenCalled();
  });

  it("repaints Telegram chrome when the app theme changes", async () => {
    const webApp = fakeWebApp();
    window.Telegram = { WebApp: webApp };
    const { initTelegramShell } = await import("./telegram");
    initTelegramShell();
    meta.content = "#f9f9f7";
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(webApp.setHeaderColor).toHaveBeenLastCalledWith("#f9f9f7");
  });

  it("skips calls an older Telegram client does not support", async () => {
    const webApp = fakeWebApp({ isVersionAtLeast: (version: string) => Number(version) <= 6.0 });
    window.Telegram = { WebApp: webApp };
    const { initTelegramShell } = await import("./telegram");
    initTelegramShell();
    expect(webApp.requestFullscreen).not.toHaveBeenCalled();
    expect(webApp.disableVerticalSwipes).not.toHaveBeenCalled();
    expect(webApp.setHeaderColor).not.toHaveBeenCalled();
  });
});
