"""Public request and response contracts for application authentication."""
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.workspace import WorkspaceKind, WorkspaceRole


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AuthenticatedUser(BaseModel):
    id: UUID
    identifier: str
    display_name: str


class WorkspaceSummary(BaseModel):
    id: UUID
    display_name: str
    kind: WorkspaceKind
    role: WorkspaceRole


class AuthSessionResponse(BaseModel):
    user: AuthenticatedUser
    workspaces: list[WorkspaceSummary]
    active_workspace: WorkspaceSummary
    csrf_token: str
