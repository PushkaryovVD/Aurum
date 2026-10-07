"""Transactional household workspace and invitation operations."""
from datetime import UTC, datetime, timedelta
import hmac
import secrets
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import (
    is_safe_text,
    valid_display_name,
    valid_normalized_identifier,
)
from app.db.seed import add_workspace_defaults
from app.models.auth import InitialOwnerBootstrap
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


class FirstOwnerBootstrapUnavailable(Exception):
    """The one-time first-owner setup code cannot be consumed."""


PRIVATE_WORKSPACE_SUFFIX = "'s private workspace"
MAX_WORKSPACE_DISPLAY_NAME_LENGTH = 100


def private_workspace_display_name(owner_display_name: str) -> str:
    """Derive a personal-workspace label within the database bound."""
    prefix_length = MAX_WORKSPACE_DISPLAY_NAME_LENGTH - len(PRIVATE_WORKSPACE_SUFFIX)
    return f"{owner_display_name[:prefix_length]}{PRIVATE_WORKSPACE_SUFFIX}"


def initial_owner_code_hmac(hmac_secret: str, raw_code: str) -> bytes:
    """Bind the generated setup capability to the installation's HMAC key."""
    return capability_hmac(hmac_secret, raw_code)


async def issue_initial_owner_bootstrap_code(
    session: AsyncSession, *, hmac_secret: str, expires_in: timedelta
) -> str | None:
    """Create a pending expiring code while no user exists, without revealing it later."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('aurum:first-owner-bootstrap:v1'))"))
    if (await session.execute(select(User.id).limit(1))).scalar_one_or_none() is not None:
        return None
    record = await session.get(InitialOwnerBootstrap, 1, with_for_update=True)
    if record is not None:
        if record.expires_at > datetime.now(UTC):
            return None
        await session.delete(record)
        await session.flush()
    raw_code = secrets.token_urlsafe(32)
    session.add(
        InitialOwnerBootstrap(
            id=1,
            code_hmac=initial_owner_code_hmac(hmac_secret, raw_code),
            expires_at=datetime.now(UTC) + expires_in,
        )
    )
    await session.flush()
    return raw_code


async def initial_owner_bootstrap_required(session: AsyncSession, *, app_auth_required: bool) -> bool:
    if not app_auth_required:
        return False
    if (await session.execute(select(User.id).limit(1))).scalar_one_or_none() is not None:
        return False
    return True


async def initial_owner_bootstrap_available(session: AsyncSession, *, app_auth_required: bool) -> bool:
    """Report whether a non-expired setup capability currently exists."""
    if not await initial_owner_bootstrap_required(session, app_auth_required=app_auth_required):
        return False
    record = await session.get(InitialOwnerBootstrap, 1)
    return record is not None and record.expires_at > datetime.now(UTC)


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
    if not 300 <= expires_in_seconds <= 2_592_000:
        raise ValueError("invitation expiry is invalid")
    normalized_recipient = valid_normalized_identifier(recipient)
    if normalized_recipient is None:
        raise ValueError("invitation recipient is invalid")
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
    normalized_recipient = valid_normalized_identifier(recipient)
    if (
        not is_safe_text(raw_token, min_length=1, max_length=1024)
        or normalized_recipient is None
    ):
        raise InvitationUnavailable
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
        or record.recipient_normalized != normalized_recipient
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
    if not is_safe_text(raw_token, min_length=1, max_length=1024):
        raise InvitationUnavailable
    normalized = valid_normalized_identifier(identifier)
    safe_display_name = valid_display_name(display_name)
    if normalized is None or safe_display_name is None:
        raise InvitationUnavailable
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
        display_name=safe_display_name,
        password_hash=password_hash,
    )
    session.add(user)
    await session.flush()
    personal = Workspace(
        kind=WorkspaceKind.PERSONAL,
        display_name=private_workspace_display_name(user.display_name),
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


async def bootstrap_first_owner(
    session: AsyncSession,
    *,
    raw_code: str,
    identifier: str,
    display_name: str,
    password_hash: str,
    default_currency: str,
    hmac_secret: str,
) -> User:
    """Atomically consume the setup code without touching legacy NULL data."""
    if not is_safe_text(raw_code, min_length=1, max_length=1024):
        raise FirstOwnerBootstrapUnavailable
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('aurum:first-owner-bootstrap:v1'))"))
    record = await session.get(InitialOwnerBootstrap, 1, with_for_update=True)
    if (
        record is None
        or not hmac.compare_digest(bytes(record.code_hmac), initial_owner_code_hmac(hmac_secret, raw_code))
        or record.expires_at <= datetime.now(UTC)
        or (await session.execute(select(User.id).limit(1))).scalar_one_or_none() is not None
    ):
        raise FirstOwnerBootstrapUnavailable

    normalized = valid_normalized_identifier(identifier)
    safe_display_name = valid_display_name(display_name)
    if normalized is None or safe_display_name is None:
        raise FirstOwnerBootstrapUnavailable

    user = User(normalized_login=normalized, display_name=safe_display_name, password_hash=password_hash)
    session.add(user)
    await session.flush()
    workspace = Workspace(
        kind=WorkspaceKind.PERSONAL,
        display_name=private_workspace_display_name(user.display_name),
        created_by_user_id=user.id,
        personal_owner_user_id=user.id,
    )
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
    user.personal_workspace_id = workspace.id
    add_workspace_defaults(session, workspace.id, default_currency)
    await session.delete(record)
    await session.flush()
    return user
