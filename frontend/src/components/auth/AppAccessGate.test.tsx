import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppAccessGate } from "./AppAccessGate";
import { setLanguage } from "@/lib/i18n";

vi.hoisted(() => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {} }) });
});

const finance = vi.fn();
let root: Root;
let container: HTMLDivElement;
let client: QueryClient;
const disabled = { app_auth_required: false, finance_access_ready: true, session_transport: "https_or_loopback", initial_owner_bootstrap_required: false, initial_owner_bootstrap_available: false };
const required = { ...disabled, app_auth_required: true, finance_access_ready: false };
const initialOwnerRequired = { ...required, initial_owner_bootstrap_required: true, initial_owner_bootstrap_available: true };
const session = { user: { id: "test-user", identifier: "test-only", display_name: "Test user" }, csrf_token: "test-only-csrf", workspaces: [], active_workspace: {} };
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function Finance() { useEffect(() => { finance(); }, []); return <div>FINANCE</div>; }
async function render(path = "/") {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => { root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppAccessGate><Finance /></AppAccessGate></MemoryRouter></QueryClientProvider>); });
}
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  setLanguage("en"); finance.mockClear();
});
afterEach(() => { if (root) act(() => root.unmount()); container?.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("does not mount protected hooks before public mode is known", async () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  await render("/settings");
  expect(finance).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Checking access");
});
it("preserves disabled-mode finance with a discoverable login link", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(disabled)));
  await render();
  expect(finance).toHaveBeenCalledTimes(1);
  expect(container.querySelector('a[href="/login"]')).not.toBeNull();
});
it("disabled login never submits credentials or mounts finance", async () => {
  const fetcher = vi.fn().mockResolvedValue(reply(disabled)); vi.stubGlobal("fetch", fetcher);
  await render("/login");
  expect(container.textContent).toContain("Individual sign-in is not enabled");
  expect(container.querySelector<HTMLInputElement>('input[type="password"]')?.disabled).toBe(true);
  await act(async () => { container.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(finance).not.toHaveBeenCalled();
});
it.each([null, {}, { ...disabled, app_auth_required: "false" }, { ...disabled, finance_access_ready: false }])("fails closed for malformed mode %j", async (body) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(body)));
  await render();
  expect(finance).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Could not verify access");
});
it.each([404, 503])("never treats status HTTP %s as legacy permission", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({}, status)));
  await render();
  expect(finance).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Could not verify access");
});

it("required mode resolves identity and never mounts finance on any protected route", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply(session));
  vi.stubGlobal("fetch", fetcher);
  await render("/transactions/import");
  expect(finance).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Session confirmed");
  expect(container.textContent).toContain("Financial space is not open yet");
  expect(container.querySelector('a[href="/"]')).toBeNull();
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual(["/api/auth/status", "/api/auth/me"]);
});
it("initial-owner setup refreshes status, verifies its server session, and never opens finance", async () => {
  const persist = vi.spyOn(Storage.prototype, "setItem");
  const fetcher = vi.fn()
    .mockResolvedValueOnce(reply(initialOwnerRequired))
    .mockResolvedValueOnce(reply(session))
    .mockResolvedValueOnce(reply(required))
    .mockResolvedValueOnce(reply(session));
  vi.stubGlobal("fetch", fetcher);
  await render("/login");
  expect(container.textContent).toContain("Initial owner setup");
  expect(container.textContent).toContain("backend startup logs");
  const form = container.querySelector("form")!;
  form.querySelector<HTMLInputElement>('[name="bootstrap_code"]')!.value = "one-time-test-code";
  form.querySelector<HTMLInputElement>('[name="display_name"]')!.value = "Test owner";
  form.querySelector<HTMLInputElement>('[name="identifier"]')!.value = "owner@example.com";
  form.querySelector<HTMLInputElement>('[name="password"]')!.value = "correct horse battery staple";
  await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  expect(fetcher.mock.calls[1][0]).toBe("/api/auth/bootstrap/initial-owner");
  expect(fetcher.mock.calls[1][1]).toMatchObject({ method: "POST", credentials: "same-origin", cache: "no-store" });
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
    bootstrap_code: "one-time-test-code",
    display_name: "Test owner",
    identifier: "owner@example.com",
    password: "correct horse battery staple",
  });
  expect(fetcher.mock.calls.slice(2).map(([path]) => path)).toEqual(["/api/auth/status", "/api/auth/me"]);
  expect(container.textContent).toContain("Session confirmed");
  expect(container.querySelector<HTMLInputElement>('[name="bootstrap_code"]')).toBeNull();
  expect(finance).not.toHaveBeenCalled();
  expect(persist).not.toHaveBeenCalled();
});
it("expired initial-owner setup stays fail-closed and tells the operator to restart backend", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ ...initialOwnerRequired, initial_owner_bootstrap_available: false })));
  await render("/login");
  expect(container.textContent).toContain("The setup code has expired");
  expect(container.querySelector<HTMLInputElement>('[name="bootstrap_code"]')?.disabled).toBe(true);
  expect(finance).not.toHaveBeenCalled();
});
it.each([403, 503])("session check HTTP %s disables credential submission", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, status)));
  await render("/login");
  expect(container.textContent).toContain("Could not verify the session");
  expect(container.querySelector<HTMLInputElement>('input[type="password"]')?.disabled).toBe(true);
  expect(finance).not.toHaveBeenCalled();
});
it("primary sign-in button has no conflicting foreground or background classes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401)));
  await render("/login");
  const button = container.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  expect(button.textContent?.trim()).not.toBe("");
  expect(button.classList.contains("text-surface-1")).toBe(true);
  expect(button.classList.contains("bg-text-primary")).toBe(true);
  expect(button.classList.contains("text-text-primary")).toBe(false);
  expect(button.classList.contains("bg-surface-1")).toBe(false);
});
it("required production transport blocks HTTP localhost without sending credentials", async () => {
  const fetcher = vi.fn().mockResolvedValue(reply({ ...required, session_transport: "https" }));
  vi.stubGlobal("fetch", fetcher);
  await render("/login");
  expect(container.textContent).toContain("Sign-in needs HTTPS");
  expect(container.querySelector<HTMLInputElement>('input[type="password"]')?.disabled).toBe(true);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
async function submitCredentials() {
  const form = container.querySelector("form")!;
  form.querySelector<HTMLInputElement>('[name="identifier"]')!.value = "test-only";
  form.querySelector<HTMLInputElement>('[name="password"]')!.value = "test-only-password";
  await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}
it("login uses real session contract, verifies cookie via me, and stores no credentials", async () => {
  const persist = vi.spyOn(Storage.prototype, "setItem");
  const fetcher = vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401))
    .mockResolvedValueOnce(reply(session)).mockResolvedValueOnce(reply(session));
  vi.stubGlobal("fetch", fetcher);
  await render("/login");
  expect(container.textContent).toContain("administrator account bootstrap is not ready");
  await submitCredentials();
  expect(fetcher.mock.calls[2][0]).toBe("/api/auth/session");
  expect(fetcher.mock.calls[2][1]).toMatchObject({ method: "POST", credentials: "same-origin", cache: "no-store", body: JSON.stringify({ identifier: "test-only", password: "test-only-password" }) });
  expect(fetcher.mock.calls[3][0]).toBe("/api/auth/me");
  expect(container.textContent).toContain("Session confirmed");
  expect(finance).not.toHaveBeenCalled();
  expect(persist).not.toHaveBeenCalled();
  expect(container.innerHTML).not.toContain("test-only-csrf");
});
it("logout sends memory-only CSRF, clears query cache, and verifies server logout", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply(session))
    .mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(reply({}, 401));
  vi.stubGlobal("fetch", fetcher);
  await render("/login"); client.setQueryData(["protected-test"], "sensitive-test-only");
  await act(async () => { Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "Sign out")!.click(); });
  expect(fetcher.mock.calls[2]).toEqual(["/api/auth/session", expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "test-only-csrf" } })]);
  expect(fetcher.mock.calls[3][0]).toBe("/api/auth/me");
  expect(client.getQueryData(["protected-test"])).toBeUndefined();
  expect(container.textContent).not.toContain("Session confirmed");
  expect(finance).not.toHaveBeenCalled();
});
it.each([401, 429, 503])("login HTTP %s is honest and clears the password field", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401)).mockResolvedValueOnce(reply({}, status)));
  await render("/login"); await submitCredentials();
  expect(container.textContent).toContain(status === 429 ? "Too many sign-in attempts" : "Could not sign in");
  expect(container.querySelector<HTMLInputElement>('[name="password"]')?.value).toBe("");
  expect(finance).not.toHaveBeenCalled();
});

it.each(["/", "/net-worth", "/crypto", "/investments", "/roi", "/accounts", "/categories", "/rules", "/cash-flow", "/transactions", "/transactions/import", "/transactions/import/csv", "/transactions/import/statements", "/reports", "/budget", "/envelopes", "/advice", "/goals", "/recurring", "/help", "/settings"])("real App never issues finance/settings queries in required mode at %s", async (path) => {
  const { default: App } = await import("@/App");
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url === "/api/auth/status") return Promise.resolve(reply(required));
    if (url === "/api/auth/me") return Promise.resolve(reply(session));
    return Promise.resolve(reply({}, 503));
  });
  vi.stubGlobal("fetch", fetcher);
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => { root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>); });
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual(["/api/auth/status", "/api/auth/me"]);
  expect(container.textContent).toContain("Financial space is not open yet");
});
it("does not mistake a POST body for an accepted cookie session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401))
    .mockResolvedValueOnce(reply(session)).mockResolvedValueOnce(reply({}, 401)));
  await render("/login"); await submitCredentials();
  expect(container.textContent).toContain("Could not verify the session");
  expect(container.textContent).not.toContain("Session confirmed");
  expect(finance).not.toHaveBeenCalled();
});
it("does not claim logout when readback finds the session still active", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply(session))
    .mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(reply(session)));
  await render("/login");
  await act(async () => { Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "Sign out")!.click(); });
  expect(container.textContent).toContain("Server sign-out is not confirmed");
  expect(finance).not.toHaveBeenCalled();
});
it("malformed session cannot claim identity", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({ user: {}, csrf_token: "" })));
  await render("/login");
  expect(container.textContent).toContain("Could not verify the session");
  expect(container.textContent).not.toContain("Session confirmed");
});

it("login trailing slash remains an entry route without finance", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(disabled)));
  await render("/login/");
  expect(finance).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Individual sign-in is not enabled");
});
it("network mode failures fail closed and an explicit retry can recover", async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new TypeError("Offline")).mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401));
  vi.stubGlobal("fetch", fetcher); await render("/settings");
  expect(container.textContent).toContain("Could not verify access");
  expect(finance).not.toHaveBeenCalled();
  await act(async () => { Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "Check again")!.click(); });
  expect(container.textContent).toContain("Financial space is not open yet");
  expect(finance).not.toHaveBeenCalled();
});
it("entry has native labelled inputs, tap targets, focus styles and RU translation", async () => {
  setLanguage("ru");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply({}, 401)));
  await render("/login");
  expect(container.textContent).toContain("Вход в Aurum");
  for (const input of container.querySelectorAll("input")) {
    expect(container.querySelector(`label[for="${input.id}"]`)).not.toBeNull();
    expect(input.className).toContain("min-h-11");
    expect(input.className).toContain("focus-visible:outline");
  }
});
it("session readback failure does not submit a password", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(reply(required)).mockRejectedValueOnce(new TypeError("Offline"));
  vi.stubGlobal("fetch", fetcher); await render("/login");
  expect(container.textContent).toContain("Could not verify the session");
  expect(container.querySelector<HTMLInputElement>('[name="password"]')?.disabled).toBe(true);
  expect(finance).not.toHaveBeenCalled();
});
it("failed server logout clears cached finance without pretending revocation", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply(session)).mockResolvedValueOnce(reply({}, 503)));
  await render("/login"); client.setQueryData(["private-test"], "test-only");
  await act(async () => { Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "Sign out")!.click(); });
  expect(client.getQueryData(["private-test"])).toBeUndefined();
  expect(container.textContent).toContain("Server sign-out is not confirmed");
});
it("a confirmed session can be rechecked and expiry cannot open finance", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(required)).mockResolvedValueOnce(reply(session)).mockResolvedValueOnce(reply({}, 401)));
  await render("/login");
  await act(async () => { Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "Check again")!.click(); });
  expect(container.textContent).not.toContain("Session confirmed");
  expect(finance).not.toHaveBeenCalled();
});
