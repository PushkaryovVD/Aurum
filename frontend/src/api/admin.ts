import { api } from "./client";
import type { WorkspaceStatus } from "@/lib/authSession";

export type AdminRole = "owner" | "editor" | "viewer";

export interface AdminUserMembership {
  workspace_id: string;
  display_name: string;
  kind: "personal" | "household";
  role: AdminRole;
  status: WorkspaceStatus;
}

export interface AdminUser {
  id: string;
  identifier: string;
  display_name: string;
  status: "active" | "disabled";
  is_admin: boolean;
  is_self: boolean;
  created_at: string;
  last_login_at: string | null;
  last_seen_at: string | null;
  memberships: AdminUserMembership[];
}

export interface AdminWorkspaceMember {
  user_id: string;
  identifier: string;
  display_name: string;
  role: AdminRole;
}

export interface AdminWorkspace {
  id: string;
  display_name: string;
  kind: "personal" | "household";
  status: WorkspaceStatus;
  blocked_at: string | null;
  created_at: string;
  members: AdminWorkspaceMember[];
}

export type AdminUserAction = "block" | "unblock" | "grant-admin" | "revoke-admin";

export const fetchAdminUsers = () => api.get<AdminUser[]>("/admin/users");
export const fetchAdminWorkspaces = () => api.get<AdminWorkspace[]>("/admin/workspaces");
export const changeAdminUser = (userId: string, action: AdminUserAction) =>
  api.post<AdminUser>(`/admin/users/${userId}/${action}`, {});
export const changeAdminWorkspace = (workspaceId: string, action: "block" | "unblock") =>
  api.post<AdminWorkspace>(`/admin/workspaces/${workspaceId}/${action}`, {});
export const adminDeleteWorkspace = (workspaceId: string, confirmName: string) =>
  api.post<void>(`/admin/workspaces/${workspaceId}/delete`, { confirm_name: confirmName });
