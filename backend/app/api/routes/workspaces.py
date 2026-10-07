"""Authenticated household workspace, membership, and invitation APIs."""
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthenticatedSession,
    auth_session_service,
    client_signal,
    get_app_settings,
    get_session,
    require_authenticated_session,
    resolve_authenticated_session,
)
from app.api.routes.auth import (
    _session_response,
    _set_session_cookie,
    parse_invitation_token,
    read_auth_json,
)
from app.core.config import Settings
from app.models.auth import SecurityAuditEvent, UserSession
from app.models.workspace import User, WorkspaceMembership, WorkspaceRole
from app.schemas.auth import AuthSessionResponse
from app.schemas.workspace import (
    HouseholdCreate,
    InvitationCreated,
    MembershipResponse,
    MembershipRoleUpdate,
    WorkspaceResponse,
)
from app.services.auth_rate_limit_service import AuthRateLimiter
from app.services.workspace_service import (
    InvitationUnavailable,
    accept_for_existing_user,
    create_household,
    create_invitation,
    require_household_owner,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
GENERIC_INVITATION_ERROR = "Invitation is not available"


def _raise_owner_error(error: Exception) -> None:
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, PermissionError):
        raise HTTPException(status_code=403, detail="Owner role required") from error
    raise HTTPException(status_code=409, detail=str(error)) from error


def invitation_limiter(settings: Settings) -> AuthRateLimiter:
    return AuthRateLimiter(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        max_attempts=settings.auth_invitation_max_attempts,
        window=timedelta(seconds=settings.auth_invitation_window_seconds),
        block_for=timedelta(seconds=settings.auth_invitation_block_seconds),
        purpose="invitation",
    )


def parse_invitation_create(
    raw_payload: Mapping[str, object] | None,
) -> tuple[str, WorkspaceRole, int] | None:
    if raw_payload is None:
        return None
    recipient = raw_payload.get("recipient")
    role = raw_payload.get("role")
    expires = raw_payload.get("expires_in_seconds", 604800)
    if (
        not isinstance(recipient, str)
        or not isinstance(role, str)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
    ):
        return None
    try:
        parsed_role = WorkspaceRole(role)
    except ValueError:
        return None
    if parsed_role not in {WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}:
        return None
    return recipient, parsed_role, expires


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: HouseholdCreate,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    try:
        workspace, membership = await create_household(
            session,
            creator_id=authenticated.user.id,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            workspace_id=workspace.id,
            event_type="workspace_created",
            outcome="success",
            target_type="workspace",
            target_id=str(workspace.id),
        )
    )
    await session.commit()
    return WorkspaceResponse(
        id=workspace.id,
        display_name=workspace.display_name,
        kind=workspace.kind,
        role=membership.role,
    )


@router.get("/{workspace_id}/members", response_model=list[MembershipResponse])
async def list_members(
    workspace_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> list[MembershipResponse]:
    try:
        await require_household_owner(
            session,
            workspace_id=workspace_id,
            user_id=authenticated.user.id,
        )
    except (LookupError, PermissionError, ValueError) as exc:
        _raise_owner_error(exc)
    rows = (
        await session.execute(
            select(WorkspaceMembership, User)
            .join(User, User.id == WorkspaceMembership.user_id)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
            .order_by(WorkspaceMembership.joined_at, WorkspaceMembership.id)
        )
    ).all()
    return [
        MembershipResponse(
            id=membership.id,
            user_id=user.id,
            identifier=user.normalized_login,
            display_name=user.display_name,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for membership, user in rows
    ]


@router.patch("/{workspace_id}/members/{membership_id}", response_model=MembershipResponse)
async def update_member(
    workspace_id: UUID,
    membership_id: UUID,
    payload: MembershipRoleUpdate,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> MembershipResponse:
    try:
        await require_household_owner(session, workspace_id=workspace_id, user_id=authenticated.user.id)
    except (LookupError, PermissionError, ValueError) as exc:
        _raise_owner_error(exc)
    membership = (
        await session.execute(
            select(WorkspaceMembership)
            .where(
                WorkspaceMembership.id == membership_id,
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership.role == WorkspaceRole.OWNER or payload.role == WorkspaceRole.OWNER:
        raise HTTPException(status_code=409, detail="Owner transfer requires a separate operation")
    membership.role = payload.role
    user = await session.get(User, membership.user_id)
    await session.commit()
    return MembershipResponse(
        id=membership.id,
        user_id=user.id,
        identifier=user.normalized_login,
        display_name=user.display_name,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.delete("/{workspace_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: UUID,
    membership_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await require_household_owner(session, workspace_id=workspace_id, user_id=authenticated.user.id)
    except (LookupError, PermissionError, ValueError) as exc:
        _raise_owner_error(exc)
    membership = (
        await session.execute(
            select(WorkspaceMembership)
            .where(
                WorkspaceMembership.id == membership_id,
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership.role == WorkspaceRole.OWNER:
        raise HTTPException(status_code=409, detail="Owner transfer requires a separate operation")
    membership.revoked_at = datetime.now(UTC)
    active_sessions = (
        await session.execute(
            select(UserSession)
            .where(UserSession.user_id == membership.user_id, UserSession.revoked_at.is_(None))
            .with_for_update()
        )
    ).scalars()
    for user_session in active_sessions:
        user_session.revoked_at = membership.revoked_at
    await session.commit()


@router.post(
    "/{workspace_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def issue_invitation(
    workspace_id: UUID,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> InvitationCreated:
    parsed = parse_invitation_create(await read_auth_json(request))
    if parsed is None:
        session.add(
            SecurityAuditEvent(
                actor_user_id=authenticated.user.id,
                event_type="invitation_issued",
                outcome="failure",
                target_type="workspace",
                target_id=str(workspace_id),
            )
        )
        await session.commit()
        raise HTTPException(status_code=422, detail="Invalid invitation request")
    recipient, role, expires_in_seconds = parsed
    try:
        record, raw_token = await create_invitation(
            session,
            workspace_id=workspace_id,
            creator_id=authenticated.user.id,
            recipient=recipient,
            role=role,
            expires_in_seconds=expires_in_seconds,
            hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        )
    except (LookupError, PermissionError, ValueError) as exc:
        session.add(
            SecurityAuditEvent(
                actor_user_id=authenticated.user.id,
                event_type="invitation_issued",
                outcome="failure",
                target_type="workspace",
                target_id=str(workspace_id),
            )
        )
        await session.commit()
        _raise_owner_error(exc)
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            workspace_id=workspace_id,
            event_type="invitation_issued",
            outcome="success",
            target_type="invitation",
            target_id=str(record.id),
        )
    )
    await session.commit()
    return InvitationCreated(
        id=record.id,
        workspace_id=record.workspace_id,
        recipient=record.recipient_normalized,
        role=record.role,
        expires_at=record.expires_at,
        token=raw_token,
    )


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    workspace_id: UUID,
    invitation_id: UUID,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await require_household_owner(session, workspace_id=workspace_id, user_id=authenticated.user.id)
    except (LookupError, PermissionError, ValueError) as exc:
        session.add(
            SecurityAuditEvent(
                actor_user_id=authenticated.user.id,
                event_type="invitation_revoked",
                outcome="failure",
                target_type="invitation",
                target_id=str(invitation_id),
            )
        )
        await session.commit()
        _raise_owner_error(exc)
    from app.models.workspace import WorkspaceInvitation

    record = (
        await session.execute(
            select(WorkspaceInvitation)
            .where(
                WorkspaceInvitation.id == invitation_id,
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.revoked_at.is_(None),
                WorkspaceInvitation.uses < WorkspaceInvitation.max_uses,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if record is None:
        session.add(
            SecurityAuditEvent(
                actor_user_id=authenticated.user.id,
                workspace_id=workspace_id,
                event_type="invitation_revoked",
                outcome="failure",
                target_type="invitation",
                target_id=str(invitation_id),
            )
        )
        await session.commit()
        raise HTTPException(status_code=404, detail=GENERIC_INVITATION_ERROR)
    record.revoked_at = datetime.now(UTC)
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            workspace_id=workspace_id,
            event_type="invitation_revoked",
            outcome="success",
            target_type="invitation",
            target_id=str(invitation_id),
        )
    )
    await session.commit()


@router.post("/invitations/accept", response_model=AuthSessionResponse)
async def accept_invitation(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    limiter = invitation_limiter(settings)
    signal = client_signal(request, settings)
    raw_payload = await read_auth_json(request)
    token = parse_invitation_token(raw_payload) if raw_payload is not None else None
    raw_token = raw_payload.get("token") if raw_payload is not None else None
    credential = raw_token if isinstance(raw_token, str) else ""
    try:
        authenticated = await resolve_authenticated_session(request, session, settings)
    except HTTPException as exc:
        await session.rollback()
        allowed, limit_state = await limiter.check_scoped(
            session,
            credential=credential,
            client_signal=signal,
        )
        if allowed:
            limiter.record_scoped_failure(session, state=limit_state)
        session.add(
            SecurityAuditEvent(
                event_type="invitation_accepted",
                outcome="failure" if allowed else "rate_limited",
            )
        )
        await session.commit()
        status_code = exc.status_code if allowed else 429
        raise HTTPException(status_code=status_code, detail=GENERIC_INVITATION_ERROR) from exc
    allowed, limit_state = await limiter.check_scoped(
        session,
        credential=credential,
        client_signal=signal,
    )
    if not allowed:
        session.add(
            SecurityAuditEvent(
                event_type="invitation_accepted",
                outcome="rate_limited",
            )
        )
        await session.commit()
        raise HTTPException(status_code=429, detail=GENERIC_INVITATION_ERROR)
    if token is None:
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(
            SecurityAuditEvent(
                actor_user_id=authenticated.user.id,
                event_type="invitation_accepted",
                outcome="failure",
            )
        )
        await session.commit()
        raise HTTPException(status_code=404, detail=GENERIC_INVITATION_ERROR)
    actor_user_id = authenticated.user.id
    try:
        invitation = await accept_for_existing_user(
            session,
            raw_token=token,
            user=authenticated.user,
            hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        )
    except (InvitationUnavailable, IntegrityError) as exc:
        # Separate invitations to the same workspace can race membership
        # creation. The active-membership unique index decides the winner.
        if isinstance(exc, IntegrityError):
            await session.rollback()
            _, limit_state = await limiter.check_scoped(
                session,
                credential=token,
                client_signal=signal,
            )
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(
            SecurityAuditEvent(
                actor_user_id=actor_user_id,
                event_type="invitation_accepted",
                outcome="failure",
            )
        )
        await session.commit()
        raise HTTPException(status_code=404, detail=GENERIC_INVITATION_ERROR) from exc

    issued = await auth_session_service(settings).rotate(
        session,
        current=authenticated.record,
        user_id=authenticated.user.id,
        client_ip=client_signal(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset_scoped(session, state=limit_state)
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            workspace_id=invitation.workspace_id,
            event_type="invitation_accepted",
            outcome="success",
            target_type="invitation",
            target_id=str(invitation.id),
        )
    )
    result = await _session_response(
        session,
        user=authenticated.user,
        csrf_token=issued.csrf_token,
        requested_workspace=None,
    )
    await session.commit()
    _set_session_cookie(response, request, settings, issued.session_token)
    return result
