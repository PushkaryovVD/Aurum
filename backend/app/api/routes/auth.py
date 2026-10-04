"""Application session login, logout, and current-user endpoints."""
from datetime import timedelta
from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SESSION_COOKIE_NAME,
    AuthenticatedSession,
    auth_session_service,
    client_signal,
    get_app_settings,
    get_session,
    request_origin,
    require_authenticated_session,
)
from app.core.config import Settings
from app.core.identity import normalize_identifier
from app.models.auth import SecurityAuditEvent
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership
from app.schemas.auth import AuthSessionResponse, AuthenticatedUser, LoginRequest, WorkspaceSummary
from app.schemas.workspace import NewAccountInvitationAccept
from app.security.auth import PasswordService
from app.services.auth_rate_limit_service import AuthRateLimiter
from app.services.workspace_service import InvitationUnavailable, bootstrap_invited_user

router = APIRouter(prefix="/auth", tags=["authentication"])
GENERIC_LOGIN_ERROR = "Unable to sign in"
ACTIVE_WORKSPACE_HEADER = "X-Aurum-Workspace"


@router.get("/status")
async def read_auth_status(
    response: Response,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, bool | str]:
    """Public mode only; financial isolation and operator bootstrap are incomplete."""
    response.headers["Cache-Control"] = "no-store"
    return {
        "app_auth_required": settings.app_auth_required,
        "finance_access_ready": False,
        "session_transport": "https" if settings.environment == "production" else "https_or_loopback",
    }


@lru_cache(maxsize=16)
def _password_context(
    memory_cost: int,
    time_cost: int,
    parallelism: int,
    hash_len: int,
    salt_len: int,
) -> tuple[PasswordService, str]:
    service = PasswordService(
        memory_cost=memory_cost,
        time_cost=time_cost,
        parallelism=parallelism,
        hash_len=hash_len,
        salt_len=salt_len,
    )
    return service, service.hash("aurum-timing-equalization-value")


def password_context(settings: Settings) -> tuple[PasswordService, str]:
    return _password_context(
        settings.auth_argon2_memory_kib,
        settings.auth_argon2_time_cost,
        settings.auth_argon2_parallelism,
        settings.auth_argon2_hash_length,
        settings.auth_argon2_salt_length,
    )


def rate_limiter(settings: Settings) -> AuthRateLimiter:
    return AuthRateLimiter(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        max_attempts=settings.auth_login_max_attempts,
        window=timedelta(seconds=settings.auth_login_window_seconds),
        block_for=timedelta(seconds=settings.auth_login_block_seconds),
    )


def invitation_rate_limiter(settings: Settings) -> AuthRateLimiter:
    return AuthRateLimiter(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        max_attempts=settings.auth_invitation_max_attempts,
        window=timedelta(seconds=settings.auth_invitation_window_seconds),
        block_for=timedelta(seconds=settings.auth_invitation_block_seconds),
        purpose="invitation",
    )


def _cookie_secure(request: Request, settings: Settings) -> bool:
    return settings.environment == "production" or request_origin(request).startswith("https://")


def _set_session_cookie(response: Response, request: Request, settings: Settings, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.auth_session_absolute_seconds,
        httponly=True,
        secure=_cookie_secure(request, settings),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(request, settings),
        samesite="lax",
        path="/",
    )


async def _session_response(
    session: AsyncSession,
    *,
    user: User,
    csrf_token: str,
    requested_workspace: str | None,
) -> AuthSessionResponse:
    statement = (
        select(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.revoked_at.is_(None),
        )
        .order_by(Workspace.created_at, Workspace.id)
    )
    rows = (await session.execute(statement)).all()
    summaries = [
        WorkspaceSummary(
            id=workspace.id,
            display_name=workspace.display_name,
            kind=workspace.kind,
            role=membership.role,
        )
        for membership, workspace in rows
    ]
    by_id = {summary.id: summary for summary in summaries}

    if requested_workspace is None:
        active_id = user.personal_workspace_id
    else:
        try:
            active_id = UUID(requested_workspace)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Workspace not found") from exc

    active_workspace = by_id.get(active_id)
    if active_workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return AuthSessionResponse(
        user=AuthenticatedUser(
            id=user.id,
            identifier=user.normalized_login,
            display_name=user.display_name,
        ),
        workspaces=summaries,
        active_workspace=active_workspace,
        csrf_token=csrf_token,
    )


@router.post("/session", response_model=AuthSessionResponse)
async def create_session(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")

    identifier = normalize_identifier(payload.identifier)
    limiter = rate_limiter(settings)
    bucket_hmac = limiter.bucket_hmac(identifier=identifier, client_signal=client_signal(request))
    allowed, limit_record = await limiter.is_allowed(session, bucket_hmac=bucket_hmac)
    if not allowed:
        session.add(SecurityAuditEvent(event_type="login", outcome="rate_limited"))
        await session.commit()
        raise HTTPException(status_code=429, detail=GENERIC_LOGIN_ERROR)

    user = (
        await session.execute(select(User).where(User.normalized_login == identifier))
    ).scalar_one_or_none()
    password_service, dummy_hash = password_context(settings)
    encoded_hash = user.password_hash if user is not None else dummy_hash
    password_valid = password_service.verify(encoded_hash, payload.password)
    if user is None or user.status != UserStatus.ACTIVE or not password_valid:
        limiter.record_failure(session, record=limit_record, bucket_hmac=bucket_hmac)
        session.add(SecurityAuditEvent(event_type="login", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if password_service.needs_rehash(user.password_hash):
        user.password_hash = password_service.hash(payload.password)

    service = auth_session_service(settings)
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    current = None
    if current_token:
        current = await service.resolve(session, token=current_token, refresh_idle=False)
    issued = await service.rotate(
        session,
        current=current,
        user_id=user.id,
        client_ip=client_signal(request),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset(session, record=limit_record)
    session.add(SecurityAuditEvent(actor_user_id=user.id, event_type="login", outcome="success"))
    result = await _session_response(
        session,
        user=user,
        csrf_token=issued.csrf_token,
        requested_workspace=request.headers.get(ACTIVE_WORKSPACE_HEADER),
    )
    await session.commit()
    _set_session_cookie(response, request, settings, issued.session_token)
    return result


@router.post("/invitations/accept", response_model=AuthSessionResponse)
async def accept_new_account_invitation(
    payload: NewAccountInvitationAccept,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Consume an invitation only as part of its explicit account-creation flow."""
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")

    identifier = normalize_identifier(payload.identifier)
    limiter = invitation_rate_limiter(settings)
    bucket_hmac = limiter.bucket_hmac(
        identifier=f"{identifier}\0{payload.token}",
        client_signal=client_signal(request),
    )
    allowed, limit_record = await limiter.is_allowed(session, bucket_hmac=bucket_hmac)
    if not allowed:
        await session.commit()
        raise HTTPException(status_code=429, detail="Invitation is not available")

    password_service, _ = password_context(settings)
    try:
        user, invitation = await bootstrap_invited_user(
            session,
            raw_token=payload.token,
            identifier=identifier,
            display_name=payload.display_name,
            password_hash=password_service.hash(payload.password),
            hmac_secret=settings.auth_hmac_secret.get_secret_value(),
            default_currency=settings.default_currency,
        )
    except (InvitationUnavailable, IntegrityError) as exc:
        # Separate invitations for one recipient can race account creation.
        # The user uniqueness constraint decides the winner; rollback keeps the
        # losing invitation unconsumed and preserves the generic response.
        if isinstance(exc, IntegrityError):
            await session.rollback()
            _, limit_record = await limiter.is_allowed(session, bucket_hmac=bucket_hmac)
        limiter.record_failure(session, record=limit_record, bucket_hmac=bucket_hmac)
        await session.commit()
        raise HTTPException(status_code=404, detail="Invitation is not available") from exc

    issued = await auth_session_service(settings).issue(
        session,
        user_id=user.id,
        client_ip=client_signal(request),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset(session, record=limit_record)
    session.add(
        SecurityAuditEvent(
            actor_user_id=user.id,
            workspace_id=invitation.workspace_id,
            event_type="invitation_accepted",
            outcome="success",
            target_type="invitation",
            target_id=str(invitation.id),
        )
    )
    result = await _session_response(
        session,
        user=user,
        csrf_token=issued.csrf_token,
        requested_workspace=None,
    )
    await session.commit()
    _set_session_cookie(response, request, settings, issued.session_token)
    return result


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    request: Request,
    response: Response,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> None:
    service = auth_session_service(settings)
    service.revoke(authenticated.record)
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            event_type="logout",
            outcome="success",
        )
    )
    await session.commit()
    _clear_session_cookie(response, request, settings)


@router.get("/me", response_model=AuthSessionResponse)
async def read_current_user(
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    csrf_token = auth_session_service(settings).csrf_token_for_session(authenticated.token)
    return await _session_response(
        session,
        user=authenticated.user,
        csrf_token=csrf_token,
        requested_workspace=request.headers.get(ACTIVE_WORKSPACE_HEADER),
    )
