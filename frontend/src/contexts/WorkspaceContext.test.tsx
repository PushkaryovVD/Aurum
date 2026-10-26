import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, setApiSessionContext } from "@/api/client";
import { useWorkspace, WorkspaceProvider } from "./WorkspaceContext";
import type { IdentitySession } from "@/lib/authSession";

const one = { id: "workspace-one", display_name: "One", kind: "personal", role: "owner", status: "active" } as const;
const two = { id: "workspace-two", display_name: "Two", kind: "household", role: "viewer", status: "active" } as const;
const session: IdentitySession = {
  user: { id: "user-one", identifier: "owner@example.com", display_name: "Owner", is_admin: false },
  csrf_token: "csrf-one",
  workspaces: [one, two],
  active_workspace: one,
};

let root: Root;
let container: HTMLDivElement;
let client: QueryClient;

function Harness({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}><WorkspaceProvider session={session} onSessionEnded={() => undefined}>{children}</WorkspaceProvider></QueryClientProvider>;
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  setApiSessionContext(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("clears cached finance and scopes the next request when switching workspace", async () => {
  const seen: string[] = [];
  vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
    seen.push(new Headers(init.headers).get("X-Aurum-Workspace") ?? "none");
    return Promise.resolve(new Response(JSON.stringify({ value: seen.length }), { status: 200 }));
  }));

  function Consumer() {
    const workspace = useWorkspace()!;
    const query = useQuery({ queryKey: ["workspace-value"], queryFn: () => api.get<{ value: number }>("/value") });
    return <button type="button" onClick={() => void workspace.switchWorkspace("workspace-two")}>
      {workspace.activeWorkspace.id}:{query.data?.value ?? "loading"}
    </button>;
  }

  setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: session.active_workspace.id });
  await act(async () => { root.render(<Harness><Consumer /></Harness>); });
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toBe("workspace-one:1")); });
  await act(async () => { container.querySelector("button")!.click(); });
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toBe("workspace-two:2")); });

  expect(seen).toEqual(["workspace-one", "workspace-two"]);
  expect(client.getQueryData(["workspace-value"])).toEqual({ value: 2 });
});

it("rejects a workspace that is not present in the verified session", async () => {
  let switchWorkspace: ((workspaceId: string) => Promise<void>) | undefined;
  function Consumer() {
    switchWorkspace = useWorkspace()!.switchWorkspace;
    return null;
  }
  await act(async () => { root.render(<Harness><Consumer /></Harness>); });
  await expect(switchWorkspace!("unknown")).rejects.toThrow("not available");
});

it("signs out with CSRF and clears protected query data", async () => {
  const ended = vi.fn();
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetcher);
  setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: session.active_workspace.id });
  client.setQueryData(["private"], "sensitive");
  function Consumer() {
    const workspace = useWorkspace()!;
    return <button type="button" onClick={() => void workspace.signOut()}>Sign out</button>;
  }
  await act(async () => {
    root.render(<QueryClientProvider client={client}><WorkspaceProvider session={session} onSessionEnded={ended}><Consumer /></WorkspaceProvider></QueryClientProvider>);
  });
  await act(async () => { container.querySelector("button")!.click(); });
  await vi.waitFor(() => expect(ended).toHaveBeenCalledOnce());

  const [url, init] = fetcher.mock.calls[0];
  const headers = new Headers(init.headers);
  expect(url).toBe("/api/auth/session");
  expect(init.method).toBe("DELETE");
  expect(headers.get("X-CSRF-Token")).toBe("csrf-one");
  expect(headers.get("X-Aurum-Workspace")).toBe("workspace-one");
  expect(client.getQueryData(["private"])).toBeUndefined();
});

it("marks the active workspace blocked when the server answers 423 and refuses to switch into it", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Workspace is blocked" }), { status: 423 })));
  let current: ReturnType<typeof useWorkspace> = null;
  function Consumer() {
    current = useWorkspace();
    const query = useQuery({ queryKey: ["blocked-probe"], queryFn: () => api.get("/accounts") });
    return <span>{current!.activeWorkspace.status}:{query.isError ? "error" : "pending"}</span>;
  }
  setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: session.active_workspace.id });
  await act(async () => { root.render(<Harness><Consumer /></Harness>); });
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toBe("blocked:error")); });
  expect(current!.workspaces.find((item) => item.id === "workspace-one")?.status).toBe("blocked");

  act(() => current!.setWorkspaceStatus("workspace-two", "blocked"));
  await expect(current!.switchWorkspace("workspace-two")).rejects.toThrow("blocked");
});

it("forgets a deleted workspace and falls back to an open one", async () => {
  let current: ReturnType<typeof useWorkspace> = null;
  function Consumer() {
    current = useWorkspace();
    return <span>{current!.activeWorkspace.id}:{current!.workspaces.length}</span>;
  }
  const familyFirst = { ...session, active_workspace: two };
  await act(async () => {
    root.render(<QueryClientProvider client={client}><WorkspaceProvider session={familyFirst} onSessionEnded={() => undefined}><Consumer /></WorkspaceProvider></QueryClientProvider>);
  });
  await act(async () => { await current!.dropWorkspace("workspace-two"); });
  expect(container.textContent).toBe("workspace-one:1");
});
