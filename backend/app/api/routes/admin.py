"""Installation administration API: users and workspaces, never finances."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedSession, get_session, require_installation_admin
from app.models.auth import SecurityAuditEvent
from app.models.workspace import User, UserStatus, Workspace, WorkspaceStatus
from app.schemas.admin import (
    AdminUser,
    AdminUserMembership,
    AdminWorkspace,
    AdminWorkspaceMember,
    WorkspaceDeleteRequest,
)
from app.services.admin_service import (
    AdminActionRefused,
    active_memberships,
    set_user_admin,
    set_user_status,
    set_workspace_status,
    user_activity,
)
from app.services.workspace_deletion_service import WorkspaceDeletionRefused, purge_household_workspace

router = APIRouter(prefix="/admin", tags=["admin"])


def audit_event(
    session: AsyncSession,
    *,
    actor_id: UUID,
    event_type: str,
    outcome: str,
    target_type: str,
    target_id: UUID,
    workspace_id: UUID | None = None,
) -> None:
    session.add(
        SecurityAuditEvent(
            actor_user_id=actor_id,
            workspace_id=workspace_id,
            event_type=event_type,
            outcome=outcome,
            target_type=target_type,
            target_id=str(target_id),
        )
    )


async def refuse(
    session: AsyncSession,
    error: Exception,
    *,
    actor_id: UUID,
    event_type: str,
    target_type: str,
    target_id: UUID,
) -> None:
    """Undo the partial change, keep an audit trail, and answer clearly."""
    await session.rollback()
    audit_event(
        session,
        actor_id=actor_id,
        event_type=event_type,
        outcome="failure",
        target_type=target_type,
        target_id=target_id,
    )
    await session.commit()
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail=f"{target_type.capitalize()} not found") from error
    if isinstance(error, PermissionError):
        raise HTTPException(status_code=403, detail="Administrator role required") from error
    raise HTTPException(status_code=409, detail=str(error)) from error


async def _admin_user(session: AsyncSession, user: User, actor_id: UUID) -> AdminUser:
    return (await _admin_users(session, actor_id, only=user.id))[0]


async def _admin_users(session: AsyncSession, actor_id: UUID, *, only: UUID | None = None) -> list[AdminUser]:
    statement = select(User).order_by(User.created_at, User.id)
    if only is not None:
        statement = statement.where(User.id == only)
    users = list((await session.execute(statement)).scalars())
    activity = await user_activity(session)
    memberships: dict[UUID, list[AdminUserMembership]] = {}
    for membership, workspace, member in await active_memberships(session):
        memberships.setdefault(member.id, []).append(
            AdminUserMembership(
                workspace_id=workspace.id,
                display_name=workspace.display_name,
                kind=workspace.kind,
                role=membership.role,
                status=workspace.status,
            )
        )
    return [
        AdminUser(
            id=user.id,
            identifier=user.normalized_login,
            display_name=user.display_name,
            status=user.status,
            is_admin=user.is_admin,
            is_self=user.id == actor_id,
            created_at=user.created_at,
            last_login_at=activity[user.id].last_login_at if user.id in activity else None,
            last_seen_at=activity[user.id].last_seen_at if user.id in activity else None,
            memberships=memberships.get(user.id, []),
        )
        for user in users
    ]


async def _admin_workspaces(session: AsyncSession, *, only: UUID | None = None) -> list[AdminWorkspace]:
    statement = select(Workspace).order_by(Workspace.kind.desc(), Workspace.created_at, Workspace.id)
    if only is not None:
        statement = statement.where(Workspace.id == only)
    workspaces = list((await session.execute(statement)).scalars())
    members: dict[UUID, list[AdminWorkspaceMember]] = {}
    for membership, workspace, user in await active_memberships(session):
        members.setdefault(workspace.id, []).append(
            AdminWorkspaceMember(
                user_id=user.id,
                identifier=user.normalized_login,
                display_name=user.display_name,
                role=membership.role,
            )
        )
    return [
        AdminWorkspace(
            id=workspace.id,
            display_name=workspace.display_name,
            kind=workspace.kind,
            status=workspace.status,
            blocked_at=workspace.blocked_at,
            created_at=workspace.created_at,
            members=members.get(workspace.id, []),
        )
        for workspace in workspaces
    ]


@router.get("/users", response_model=list[AdminUser])
async def list_users(
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUser]:
    return await _admin_users(session, authenticated.user.id)


async def _change_user(
    session: AsyncSession,
    authenticated: AuthenticatedSession,
    user_id: UUID,
    *,
    event_type: str,
    user_status: UserStatus | None = None,
    is_admin: bool | None = None,
) -> AdminUser:
    actor_id = authenticated.user.id
    try:
        if user_status is not None:
            user = await set_user_status(session, actor_id=actor_id, target_id=user_id, status=user_status)
        else:
            assert is_admin is not None
            user = await set_user_admin(session, actor_id=actor_id, target_id=user_id, is_admin=is_admin)
    except (LookupError, PermissionError, AdminActionRefused) as exc:
        await refuse(session, exc, actor_id=actor_id, event_type=event_type, target_type="user", target_id=user_id)
    audit_event(session, actor_id=actor_id, event_type=event_type, outcome="success", target_type="user", target_id=user_id)
    await session.commit()
    return await _admin_user(session, user, actor_id)


@router.post("/users/{user_id}/block", response_model=AdminUser)
async def block_user(
    user_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    return await _change_user(session, authenticated, user_id, event_type="admin_user_blocked", user_status=UserStatus.DISABLED)


@router.post("/users/{user_id}/unblock", response_model=AdminUser)
async def unblock_user(
    user_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    return await _change_user(session, authenticated, user_id, event_type="admin_user_unblocked", user_status=UserStatus.ACTIVE)


@router.post("/users/{user_id}/grant-admin", response_model=AdminUser)
async def grant_admin(
    user_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    return await _change_user(session, authenticated, user_id, event_type="admin_role_granted", is_admin=True)


@router.post("/users/{user_id}/revoke-admin", response_model=AdminUser)
async def revoke_admin(
    user_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    return await _change_user(session, authenticated, user_id, event_type="admin_role_revoked", is_admin=False)


@router.get("/workspaces", response_model=list[AdminWorkspace])
async def list_workspaces(
    _authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminWorkspace]:
    return await _admin_workspaces(session)


async def _change_workspace(
    session: AsyncSession,
    authenticated: AuthenticatedSession,
    workspace_id: UUID,
    *,
    event_type: str,
    workspace_status: WorkspaceStatus,
) -> AdminWorkspace:
    actor_id = authenticated.user.id
    try:
        await set_workspace_status(session, workspace_id=workspace_id, status=workspace_status)
    except LookupError as exc:
        await refuse(session, exc, actor_id=actor_id, event_type=event_type, target_type="workspace", target_id=workspace_id)
    audit_event(
        session,
        actor_id=actor_id,
        event_type=event_type,
        outcome="success",
        target_type="workspace",
        target_id=workspace_id,
        workspace_id=workspace_id,
    )
    await session.commit()
    return (await _admin_workspaces(session, only=workspace_id))[0]


@router.post("/workspaces/{workspace_id}/block", response_model=AdminWorkspace)
async def block_workspace(
    workspace_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminWorkspace:
    return await _change_workspace(
        session, authenticated, workspace_id, event_type="admin_workspace_blocked", workspace_status=WorkspaceStatus.BLOCKED
    )


@router.post("/workspaces/{workspace_id}/unblock", response_model=AdminWorkspace)
async def unblock_workspace(
    workspace_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminWorkspace:
    return await _change_workspace(
        session, authenticated, workspace_id, event_type="admin_workspace_unblocked", workspace_status=WorkspaceStatus.ACTIVE
    )


async def delete_workspace_permanently(
    session: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    confirm_name: str,
    event_type: str,
) -> None:
    """Shared by the admin and owner routes: one transaction, audited either way."""
    try:
        try:
            await purge_household_workspace(session, workspace_id=workspace_id, confirm_name=confirm_name)
        except IntegrityError as exc:
            # Another workspace still references these rows; nothing is removed.
            raise WorkspaceDeletionRefused("Workspace data is still referenced elsewhere") from exc
    except (LookupError, WorkspaceDeletionRefused) as exc:
        await refuse(session, exc, actor_id=actor_id, event_type=event_type, target_type="workspace", target_id=workspace_id)
    audit_event(
        session,
        actor_id=actor_id,
        event_type=event_type,
        outcome="success",
        target_type="workspace",
        target_id=workspace_id,
    )
    await session.commit()


@router.post("/workspaces/{workspace_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: UUID,
    payload: WorkspaceDeleteRequest,
    authenticated: AuthenticatedSession = Depends(require_installation_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_workspace_permanently(
        session,
        actor_id=authenticated.user.id,
        workspace_id=workspace_id,
        confirm_name=payload.confirm_name,
        event_type="admin_workspace_deleted",
    )
