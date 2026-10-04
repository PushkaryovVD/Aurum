"""User identities, private workspaces, and workspace memberships."""
from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceKind(str, enum.Enum):
    PERSONAL = "personal"
    HOUSEHOLD = "household"


class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


def _enum_values(enum_type: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_type]


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "personal_workspace_id",
            name="uq_users_personal_workspace_id",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    normalized_login: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            native_enum=False,
            length=10,
            create_constraint=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    personal_workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_users_personal_workspace_id_workspaces",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'personal' AND personal_owner_user_id IS NOT NULL) "
            "OR (kind = 'household' AND personal_owner_user_id IS NULL)",
            name="ck_workspaces_personal_owner_matches_kind",
        ),
        Index(
            "uq_workspaces_personal_owner",
            "personal_owner_user_id",
            unique=True,
            postgresql_where=text("kind = 'personal'"),
        ),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[WorkspaceKind] = mapped_column(
        Enum(
            WorkspaceKind,
            name="workspace_kind",
            native_enum=False,
            length=10,
            create_constraint=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_workspaces_created_by_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )
    personal_owner_user_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_workspaces_personal_owner_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )


class WorkspaceMembership(Base, TimestampMixin):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        Index(
            "uq_workspace_memberships_active_user",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_workspace_memberships_workspace_id_workspaces",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )
    user_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_workspace_memberships_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(
            WorkspaceRole,
            name="workspace_role",
            native_enum=False,
            length=10,
            create_constraint=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkspaceInvitation(Base, TimestampMixin):
    __tablename__ = "workspace_invitations"
    __table_args__ = (
        UniqueConstraint("token_hmac", name="uq_workspace_invitations_token_hmac"),
        CheckConstraint("role IN ('editor', 'viewer')", name="ck_workspace_invitations_role"),
        CheckConstraint("max_uses = 1", name="ck_workspace_invitations_single_use"),
        CheckConstraint("uses >= 0 AND uses <= max_uses", name="ck_workspace_invitations_uses"),
        Index("ix_workspace_invitations_workspace_id", "workspace_id"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_workspace_invitations_workspace_id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(
            WorkspaceRole,
            name="workspace_invitation_role",
            native_enum=False,
            length=10,
            create_constraint=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_workspace_invitations_created_by_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    accepted_by_user_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_workspace_invitations_accepted_by_user_id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
