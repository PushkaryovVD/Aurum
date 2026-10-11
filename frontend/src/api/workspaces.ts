import { api } from "./client";
import type { IdentitySession, WorkspaceSummary } from "@/lib/authSession";

export type WorkspaceRole = "owner" | "editor" | "viewer";

export interface WorkspaceMember {
  id: string;
  user_id: string;
  identifier: string;
  display_name: string;
  role: WorkspaceRole;
  joined_at: string;
}

export interface WorkspaceInvitation {
  id: string;
  workspace_id: string;
  recipient: string;
  role: WorkspaceRole;
  expires_at: string;
  token: string;
}

export const createWorkspace = (displayName: string) =>
  api.post<WorkspaceSummary>("/workspaces", { display_name: displayName });
export const fetchWorkspaceMembers = (workspaceId: string) =>
  api.get<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`);
export const updateWorkspaceMember = (workspaceId: string, membershipId: string, role: "editor" | "viewer") =>
  api.patch<WorkspaceMember>(`/workspaces/${workspaceId}/members/${membershipId}`, { role });
export const removeWorkspaceMember = (workspaceId: string, membershipId: string) =>
  api.delete<void>(`/workspaces/${workspaceId}/members/${membershipId}`);
export const createWorkspaceInvitation = (workspaceId: string, recipient: string, role: "editor" | "viewer") =>
  api.post<WorkspaceInvitation>(`/workspaces/${workspaceId}/invitations`, { recipient, role });
export const acceptWorkspaceInvitation = (token: string) =>
  api.post<IdentitySession>("/workspaces/invitations/accept", { token });
export const fetchIdentitySession = () => api.get<IdentitySession>("/auth/me");
