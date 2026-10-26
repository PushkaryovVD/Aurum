/**
 * Telegram Mini App shell: makes Aurum look like a standalone app when it is
 * opened inside Telegram (full screen, matching colours, native back button,
 * content kept clear of Telegram's own overlay buttons).
 *
 * Everything here is a no-op in an ordinary browser: telegram-web-app.js
 * defines `window.Telegram.WebApp` everywhere, but `initData` is only filled
 * in when Telegram actually launched the page.
 */

type TelegramEvent = "fullscreenChanged" | "fullscreenFailed" | "safeAreaChanged" | "contentSafeAreaChanged" | "backButtonClicked";

export interface TelegramWebApp {
  initData?: string;
  platform?: string;
  isFullscreen?: boolean;
  ready?: () => void;
  expand?: () => void;
  isVersionAtLeast?: (version: string) => boolean;
  requestFullscreen?: () => void;
  disableVerticalSwipes?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  onEvent?: (event: TelegramEvent, handler: () => void) => void;
  offEvent?: (event: TelegramEvent, handler: () => void) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (handler: () => void) => void;
    offClick: (handler: () => void) => void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

/** The Mini App API, or null when the page was not launched by Telegram. */
export function telegramWebApp(): TelegramWebApp | null {
  const webApp = window.Telegram?.WebApp;
  return webApp?.initData ? webApp : null;
}

function supports(webApp: TelegramWebApp, version: string): boolean {
  return webApp.isVersionAtLeast?.(version) ?? false;
}

// Telegram accepts only #RRGGBB. The <meta name="theme-color"> is kept equal
// to --surface-0 by lib/theme.ts, so it is the single source of the colour.
function currentSurfaceColor(): string | null {
  const value = document.querySelector('meta[name="theme-color"]')?.getAttribute("content")?.trim() ?? "";
  return /^#[0-9a-f]{6}$/i.test(value) ? value : null;
}

function paintChrome(webApp: TelegramWebApp): void {
  const color = currentSurfaceColor();
  if (!color || !supports(webApp, "6.1")) return;
  webApp.setHeaderColor?.(color);
  webApp.setBackgroundColor?.(color);
  if (supports(webApp, "7.10")) webApp.setBottomBarColor?.(color);
}

// Full screen is meant for phones; on desktop Telegram it would cover the
// whole monitor, so there the regular expanded panel is kept.
const FULLSCREEN_PLATFORMS = new Set(["ios", "android", "android_x"]);

let initialized = false;

/** Call once at startup. Returns true when running inside Telegram. */
export function initTelegramShell(): boolean {
  const webApp = telegramWebApp();
  if (!webApp || initialized) return Boolean(webApp);
  initialized = true;
  const root = document.documentElement;
  root.classList.add("tg-app");

  webApp.ready?.();
  webApp.expand?.();
  // Scrolling a long list must not swipe the whole app closed.
  if (supports(webApp, "7.7")) webApp.disableVerticalSwipes?.();

  const syncFullscreen = () => root.classList.toggle("tg-fullscreen", Boolean(webApp.isFullscreen));
  if (supports(webApp, "8.0")) {
    webApp.onEvent?.("fullscreenChanged", syncFullscreen);
    if (FULLSCREEN_PLATFORMS.has(webApp.platform ?? "")) webApp.requestFullscreen?.();
  }
  syncFullscreen();

  paintChrome(webApp);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) new MutationObserver(() => paintChrome(webApp)).observe(meta, { attributes: true, attributeFilter: ["content"] });
  return true;
}
