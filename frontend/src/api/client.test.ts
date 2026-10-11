import { afterEach, describe, expect, it, vi } from "vitest";
import { api, setApiSessionContext } from "./client";

afterEach(() => {
  setApiSessionContext(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API session context", () => {
  it("scopes reads to the active workspace without sending CSRF", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
    vi.stubGlobal("fetch", fetcher);
    setApiSessionContext({ csrfToken: "csrf-one", workspaceId: "workspace-one" });

    await api.get("/accounts");

    const [, init] = fetcher.mock.calls[0];
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe("same-origin");
    expect(headers.get("X-Aurum-Workspace")).toBe("workspace-one");
    expect(headers.has("X-CSRF-Token")).toBe(false);
  });

  it("adds memory-only CSRF to mutations and follows workspace changes", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
    vi.stubGlobal("fetch", fetcher);
    setApiSessionContext({ csrfToken: "csrf-one", workspaceId: "workspace-one" });
    await api.post("/accounts", { name: "Checking" });
    setApiSessionContext({ csrfToken: "csrf-one", workspaceId: "workspace-two" });
    await api.delete("/accounts/account-one");

    const first = new Headers(fetcher.mock.calls[0][1].headers);
    const second = new Headers(fetcher.mock.calls[1][1].headers);
    expect(first.get("X-Aurum-Workspace")).toBe("workspace-one");
    expect(first.get("X-CSRF-Token")).toBe("csrf-one");
    expect(second.get("X-Aurum-Workspace")).toBe("workspace-two");
    expect(second.get("X-CSRF-Token")).toBe("csrf-one");
  });

  it("does not leak session headers after the context is cleared", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
    vi.stubGlobal("fetch", fetcher);
    setApiSessionContext({ csrfToken: "csrf-one", workspaceId: "workspace-one" });
    setApiSessionContext(null);
    await api.post("/accounts", {});

    const headers = new Headers(fetcher.mock.calls[0][1].headers);
    expect(headers.has("X-Aurum-Workspace")).toBe(false);
    expect(headers.has("X-CSRF-Token")).toBe(false);
  });
});
