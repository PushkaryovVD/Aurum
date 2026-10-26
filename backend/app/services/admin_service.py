"""Installation administration: users and workspaces as containers.

Nothing here reads a workspace's financial rows; administrators see who exists,
which spaces exist and who belongs where, and can freeze or remove them.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import UserSession
from app.models.workspace import (
    User,
    UserStatus,
    Workspace,
    WorkspaceMembership,
    WorkspaceStatus,
)


class AdminActionRefused(Exception):
    """A safety rule forbids the requested administrative change."""


@dataclass(frozen=True, slots=True)
class UserActivity:
    last_login_at: datetime | None
    last_seen_at: datetime | None


async def _lock_active_admin_ids(session: AsyncSession) -> set[UUID]:
    """Serialize admin-role changes so two admins cannot demote each other at once."""
    rows = await session.execute(
        select(User.id)
        .where(User.is_admin.is_(True), User.status == UserStatus.ACTIVE)
        .order_by(User.id)
        .with_for_update()
    )
    return set(rows.scalars())


async def _lock_target_user(session: AsyncSession, user_id: UUID) -> User:
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if user is None:
        raise LookupError("user")
    return user


async def _require_actor_still_admin(session: AsyncSession, actor_id: UUID) -> set[UUID]:
    admins = await _lock_active_admin_ids(session)
    if actor_id not in admins:
        # The actor lost the role after their request was authenticated.
        raise PermissionError("administrator role required")
    return admins


async def set_user_status(
    session: AsyncSession,
    *,
    actor_id: UUID,
    target_id: UUID,
    status: UserStatus,
) -> User:
    """Block or unblock a user; blocking revokes every session immediately."""
    admins = await _require_actor_still_admin(session, actor_id)
    if target_id == actor_id:
        raise AdminActionRefused("You cannot block or unblock yourself")
    target = await _lock_target_user(session, target_id)
    if status == UserStatus.DISABLED and target.id in admins and len(admins - {target.id}) == 0:
        raise AdminActionRefused("The last administrator cannot be blocked")
    target.status = status
    if status == UserStatus.DISABLED:
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
    await session.flush()
    return target


async def set_user_admin(
    session: AsyncSession,
    *,
    actor_id: UUID,
    target_id: UUID,
    is_admin: bool,
) -> User:
    admins = await _require_actor_still_admin(session, actor_id)
    if target_id == actor_id:
        raise AdminActionRefused("You cannot change your own administrator role")
    target = await _lock_target_user(session, target_id)
    if is_admin and target.status != UserStatus.ACTIVE:
        raise AdminActionRefused("Unblock the user before granting administrator role")
    if not is_admin and target.id in admins and len(admins - {target.id}) == 0:
        raise AdminActionRefused("The last administrator cannot be demoted")
    target.is_admin = is_admin
    await session.flush()
    return target


async def set_workspace_status(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: WorkspaceStatus,
) -> Workspace:
    workspace = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    ).scalar_one_or_none()
    if workspace is None:
        raise LookupError("workspace")
    workspace.status = status
    workspace.blocked_at = datetime.now(UTC) if status == WorkspaceStatus.BLOCKED else None
    await session.flush()
    return workspace


async def user_activity(session: AsyncSession) -> dict[UUID, UserActivity]:
    rows = await session.execute(
        select(UserSession.user_id, func.max(UserSession.created_at), func.max(UserSession.last_seen_at))
        .group_by(UserSession.user_id)
    )
    return {user_id: UserActivity(last_login_at=login, last_seen_at=seen) for user_id, login, seen in rows.all()}


async def active_memberships(session: AsyncSession) -> list[tuple[WorkspaceMembership, Workspace, User]]:
    rows = await session.execute(
        select(WorkspaceMembership, Workspace, User)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.revoked_at.is_(None))
        .order_by(Workspace.kind.desc(), Workspace.display_name, WorkspaceMembership.joined_at)
    )
    return [(membership, workspace, user) for membership, workspace, user in rows.all()]
