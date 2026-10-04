"""Request and response contracts for household workspace administration."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.workspace import WorkspaceKind, WorkspaceRole


class HouseholdCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class WorkspaceResponse(BaseModel):
    id: UUID
    display_name: str
    kind: WorkspaceKind
    role: WorkspaceRole


class MembershipResponse(BaseModel):
    id: UUID
    user_id: UUID
    identifier: str
    display_name: str
    role: WorkspaceRole
    joined_at: datetime


class MembershipRoleUpdate(BaseModel):
    role: WorkspaceRole


class InvitationCreate(BaseModel):
    recipient: str = Field(min_length=1, max_length=320)
    role: WorkspaceRole
    expires_in_seconds: int = Field(default=604800, ge=300, le=2592000)


class InvitationCreated(BaseModel):
    id: UUID
    workspace_id: UUID
    recipient: str
    role: WorkspaceRole
    expires_at: datetime
    token: str


class InvitationAccept(BaseModel):
    # Empty strings use the same non-disclosing lookup path as unknown tokens.
    token: str = Field(max_length=1024)


class NewAccountInvitationAccept(InvitationAccept):
    identifier: str = Field(min_length=1, max_length=320)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=1024)
