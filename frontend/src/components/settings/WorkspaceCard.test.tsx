import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "@/lib/i18n";

vi.hoisted(() => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {} }) });
});

const createWorkspaceInvitation = vi.fn();
vi.mock("@/api/workspaces", () => ({
  acceptWorkspaceInvitation: vi.fn(),
  createWorkspace: vi.fn(),
  createWorkspaceInvitation: (...args: unknown[]) => createWorkspaceInvitation(...args),
  fetchIdentitySession: vi.fn(),
  fetchWorkspaceMembers: vi.fn().mockResolvedValue([]),
  removeWorkspaceMember: vi.fn(),
  updateWorkspaceMember: vi.fn(),
}));

const personal = { id: "ws-personal", display_name: "Personal", kind: "personal", role: "owner" };
const family = { id: "ws-family", display_name: "Family", kind: "household", role: "owner" };
const parents = { id: "ws-parents", display_name: "Parents", kind: "household", role: "owner" };
const friends = { id: "ws-friends", display_name: "Friends", kind: "household", role: "editor" };
let workspaceValue: Record<string, unknown> | null = null;
vi.mock("@/contexts/WorkspaceContext", () => ({ useWorkspace: () => workspaceValue }));

const { WorkspaceCard } = await import("./WorkspaceCard");

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root | null = null;
let container: HTMLDivElement | null = null;

function setWorkspaces(list: typeof personal[], active = list[0]) {
  workspaceValue = {
    user: { id: "u", identifier: "owner@example.com", display_name: "Owner" },
    workspaces: list,
    activeWorkspace: active,
    replaceSession: vi.fn(),
    signOut: vi.fn(),
  };
}

async function render() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => { root?.render(<QueryClientProvider client={client}><WorkspaceCard /></QueryClientProvider>); });
  return container;
}

beforeEach(() => { setLanguage("en"); createWorkspaceInvitation.mockReset(); });
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  setLanguage("ru");
});

it("explains that a family space is needed before anyone can be invited", async () => {
  setWorkspaces([personal]);
  const view = await render();
  expect(view.textContent).toContain("first create a family space");
  expect(view.querySelector('[name="recipient"]')).toBeNull();
});

it("invites into a chosen owned family space even while a personal space is active", async () => {
  setWorkspaces([personal, family, parents, friends], personal);
  createWorkspaceInvitation.mockResolvedValue({
    id: "inv", workspace_id: "ws-parents", recipient: "guest@example.com", role: "viewer",
    expires_at: "2026-11-01T00:00:00Z", token: "test-only-token", email_sent: true,
  });
  const view = await render();
  const select = view.querySelector<HTMLSelectElement>('[name="workspace"]')!;
  // Only spaces this user owns are offered; editor access cannot be re-shared.
  expect(Array.from(select.options).map((option) => option.textContent)).toEqual(["Family", "Parents"]);
  select.value = "ws-parents";
  view.querySelector<HTMLInputElement>('[name="recipient"]')!.value = "guest@example.com";
  view.querySelector<HTMLSelectElement>('[name="role"]')!.value = "viewer";
  const form = select.closest("form")!;
  await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  expect(createWorkspaceInvitation).toHaveBeenCalledWith("ws-parents", "guest@example.com", "viewer");
  expect(view.textContent).toContain("The invitation was e-mailed to guest@example.com");
  expect(view.textContent).toContain("/login#invite=test-only-token");
});
