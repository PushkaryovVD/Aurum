export type WorkspaceStatus = "active" | "blocked";

export interface WorkspaceSummary {
  id: string;
  display_name: string;
  kind: "personal" | "household";
  role: "owner" | "editor" | "viewer";
  /** An administrator can block a workspace; its data stays but nobody can open it. */
  status: WorkspaceStatus;
}

export interface IdentitySession {
  /** `is_admin` only shapes the UI; the server re-checks every admin call. */
  user: { id: string; identifier: string; display_name: string; is_admin: boolean };
  csrf_token: string;
  workspaces: WorkspaceSummary[];
  active_workspace: WorkspaceSummary;
}

function parseWorkspace(value: unknown): WorkspaceSummary {
  const workspace = value as Partial<WorkspaceSummary> | null;
  if (!workspace || typeof workspace.id !== "string" || !workspace.id ||
      typeof workspace.display_name !== "string" || !workspace.display_name ||
      !["personal", "household"].includes(String(workspace.kind)) ||
      !["owner", "editor", "viewer"].includes(String(workspace.role)) ||
      (workspace.status !== undefined && !["active", "blocked"].includes(String(workspace.status)))) {
    throw new Error("Invalid workspace session");
  }
  return {
    id: workspace.id,
    display_name: workspace.display_name,
    kind: workspace.kind as WorkspaceSummary["kind"],
    role: workspace.role as WorkspaceSummary["role"],
    // Older servers do not report a status; their workspaces are all open.
    status: (workspace.status ?? "active") as WorkspaceStatus,
  };
}

export function parseSession(value: unknown): IdentitySession {
  const data = value as Partial<IdentitySession> | null;
  if (!data || !data.user || typeof data.user.id !== "string" || !data.user.id ||
      typeof data.user.identifier !== "string" || typeof data.user.display_name !== "string" ||
      typeof data.csrf_token !== "string" || !data.csrf_token || !Array.isArray(data.workspaces)) {
    throw new Error("Invalid identity session");
  }
  const workspaces = data.workspaces.map(parseWorkspace);
  const activeWorkspace = parseWorkspace(data.active_workspace);
  if (!workspaces.some((workspace) => workspace.id === activeWorkspace.id)) {
    throw new Error("Active workspace is not available to this session");
  }
  return {
    user: {
      id: data.user.id,
      identifier: data.user.identifier,
      display_name: data.user.display_name,
      is_admin: data.user.is_admin === true,
    },
    csrf_token: data.csrf_token,
    workspaces,
    active_workspace: activeWorkspace,
  };
}
