export interface WorkspaceSummary {
  id: string;
  display_name: string;
  kind: string;
  role: string;
}

export interface IdentitySession {
  user: { id: string; identifier: string; display_name: string };
  csrf_token: string;
  workspaces: WorkspaceSummary[];
  active_workspace: WorkspaceSummary;
}

function parseWorkspace(value: unknown): WorkspaceSummary {
  const workspace = value as Partial<WorkspaceSummary> | null;
  if (!workspace || typeof workspace.id !== "string" || !workspace.id ||
      typeof workspace.display_name !== "string" || !workspace.display_name ||
      typeof workspace.kind !== "string" || !workspace.kind ||
      typeof workspace.role !== "string" || !workspace.role) {
    throw new Error("Invalid workspace session");
  }
  return {
    id: workspace.id,
    display_name: workspace.display_name,
    kind: workspace.kind,
    role: workspace.role,
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
    user: data.user,
    csrf_token: data.csrf_token,
    workspaces,
    active_workspace: activeWorkspace,
  };
}
