"""Transactional household workspace and invitation operations."""
from datetime import UTC, datetime, timedelta
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import normalize_identifier
from app.db.seed import add_workspace_defaults
from app.models.workspace import (
    User,
    Workspace,
    WorkspaceInvitation,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRole,
)
from app.security.auth import capability_hmac


class InvitationUnavailable(Exception):
    """Non-disclosing invitation failure used by both acceptance paths."""


async def require_household_owner(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> Workspace:
    workspace = (
        await session.execute(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise LookupError("workspace")
    membership = (
        await session.execute(
            select(WorkspaceMembership)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if membership is None:
        raise LookupError("workspace")
    if workspace.kind != WorkspaceKind.HOUSEHOLD:
        raise ValueError("personal workspace cannot be member-managed")
    if membership.role != WorkspaceRole.OWNER:
        raise PermissionError("owner role required")
    return workspace


async def create_household(
    session: AsyncSession,
    *,
    creator_id: UUID,
    display_name: str,
) -> tuple[Workspace, WorkspaceMembership]:
    normalized_name = display_name.strip()
    if not normalized_name:
        raise ValueError("workspace display name must not be blank")
    workspace = Workspace(
        kind=WorkspaceKind.HOUSEHOLD,
        display_name=normalized_name,
        created_by_user_id=creator_id,
    )
    session.add(workspace)
    await session.flush()
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=creator_id,
        role=WorkspaceRole.OWNER,
    )
    session.add(membership)
    await session.flush()
    return workspace, membership


async def create_invitation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    creator_id: UUID,
    recipient: str,
    role: WorkspaceRole,
    expires_in_seconds: int,
    hmac_secret: str,
) -> tuple[WorkspaceInvitation, str]:
    await require_household_owner(
        session,
        workspace_id=workspace_id,
        user_id=creator_id,
    )
    if role not in {WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}:
        raise ValueError("invitation role must be editor or viewer")
    normalized_recipient = normalize_identifier(recipient)
    if not normalized_recipient:
        raise ValueError("invitation recipient must not be blank")
    raw_token = secrets.token_urlsafe(32)
    record = WorkspaceInvitation(
        workspace_id=workspace_id,
        recipient_normalized=normalized_recipient,
        role=role,
        token_hmac=capability_hmac(hmac_secret, raw_token),
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        created_by_user_id=creator_id,
    )
    session.add(record)
    await session.flush()
    return record, raw_token


async def lock_available_invitation(
    session: AsyncSession,
    *,
    raw_token: str,
    recipient: str,
    hmac_secret: str,
) -> WorkspaceInvitation:
    record = (
        await session.execute(
            select(WorkspaceInvitation)
            .where(WorkspaceInvitation.token_hmac == capability_hmac(hmac_secret, raw_token))
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        record is None
        or record.recipient_normalized != normalize_identifier(recipient)
        or record.revoked_at is not None
        or record.expires_at <= now
        or record.uses >= record.max_uses
    ):
        raise InvitationUnavailable
    workspace = await session.get(Workspace, record.workspace_id)
    if workspace is None or workspace.kind != WorkspaceKind.HOUSEHOLD:
        raise InvitationUnavailable
    return record


async def accept_for_existing_user(
    session: AsyncSession,
    *,
    raw_token: str,
    user: User,
    hmac_secret: str,
) -> WorkspaceInvitation:
    invitation = await lock_available_invitation(
        session,
        raw_token=raw_token,
        recipient=user.normalized_login,
        hmac_secret=hmac_secret,
    )
    existing = (
        await session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == invitation.workspace_id,
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise InvitationUnavailable
    session.add(
        WorkspaceMembership(
            workspace_id=invitation.workspace_id,
            user_id=user.id,
            role=invitation.role,
        )
    )
    invitation.uses += 1
    invitation.accepted_by_user_id = user.id
    invitation.accepted_at = datetime.now(UTC)
    await session.flush()
    return invitation


async def bootstrap_invited_user(
    session: AsyncSession,
    *,
    raw_token: str,
    identifier: str,
    display_name: str,
    password_hash: str,
    hmac_secret: str,
    default_currency: str = "KZT",
) -> tuple[User, WorkspaceInvitation]:
    normalized = normalize_identifier(identifier)
    invitation = await lock_available_invitation(
        session,
        raw_token=raw_token,
        recipient=normalized,
        hmac_secret=hmac_secret,
    )
    if (await session.execute(select(User.id).where(User.normalized_login == normalized))).scalar_one_or_none():
        raise InvitationUnavailable

    user = User(
        normalized_login=normalized,
        display_name=display_name.strip(),
        password_hash=password_hash,
    )
    session.add(user)
    await session.flush()
    personal = Workspace(
        kind=WorkspaceKind.PERSONAL,
        display_name=f"{user.display_name}'s private workspace",
        created_by_user_id=user.id,
        personal_owner_user_id=user.id,
    )
    session.add(personal)
    await session.flush()
    session.add_all(
        [
            WorkspaceMembership(
                workspace_id=personal.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            ),
            WorkspaceMembership(
                workspace_id=invitation.workspace_id,
                user_id=user.id,
                role=invitation.role,
            ),
        ]
    )
    user.personal_workspace_id = personal.id
    add_workspace_defaults(session, personal.id, default_currency)
    invitation.uses += 1
    invitation.accepted_by_user_id = user.id
    invitation.accepted_at = datetime.now(UTC)
    await session.flush()
    return user, invitation
