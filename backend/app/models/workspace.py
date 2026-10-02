"""User identities, private workspaces, and workspace memberships."""
from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, UniqueConstraint, text
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
