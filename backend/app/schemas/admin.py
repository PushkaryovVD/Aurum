"""Contracts for installation administration (no financial data)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.workspace import UserStatus, WorkspaceKind, WorkspaceRole, WorkspaceStatus


class AdminUserMembership(BaseModel):
    workspace_id: UUID
    display_name: str
    kind: WorkspaceKind
    role: WorkspaceRole
    status: WorkspaceStatus


class AdminUser(BaseModel):
    id: UUID
    identifier: str
    display_name: str
    status: UserStatus
    is_admin: bool
    is_self: bool
    created_at: datetime
    # Derived from server-side sessions; None when the user never signed in.
    last_login_at: datetime | None
    last_seen_at: datetime | None
    memberships: list[AdminUserMembership]


class AdminWorkspaceMember(BaseModel):
    user_id: UUID
    identifier: str
    display_name: str
    role: WorkspaceRole


class AdminWorkspace(BaseModel):
    id: UUID
    display_name: str
    kind: WorkspaceKind
    status: WorkspaceStatus
    blocked_at: datetime | None
    created_at: datetime
    members: list[AdminWorkspaceMember]


class WorkspaceDeleteRequest(BaseModel):
    # The exact workspace name, typed by a human as a deliberate confirmation.
    confirm_name: str = Field(min_length=1, max_length=100)
