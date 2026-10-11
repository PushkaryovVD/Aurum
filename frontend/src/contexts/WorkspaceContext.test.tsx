import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, setApiSessionContext } from "@/api/client";
import { useWorkspace, WorkspaceProvider } from "./WorkspaceContext";
import type { IdentitySession } from "@/lib/authSession";

const one = { id: "workspace-one", display_name: "One", kind: "personal", role: "owner" };
const two = { id: "workspace-two", display_name: "Two", kind: "shared", role: "member" };
const session: IdentitySession = {
  user: { id: "user-one", identifier: "owner@example.com", display_name: "Owner" },
  csrf_token: "csrf-one",
  workspaces: [one, two],
  active_workspace: one,
};

let root: Root;
let container: HTMLDivElement;
let client: QueryClient;

function Harness({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}><WorkspaceProvider session={session}>{children}</WorkspaceProvider></QueryClientProvider>;
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
