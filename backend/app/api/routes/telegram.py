"""Telegram account linking and passwordless Mini App session exchange."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SESSION_COOKIE_NAME,
    AuthenticatedSession,
    RequestWorkspace,
    auth_session_service,
    client_signal,
    credential_transport_allowed,
    get_app_settings,
    get_request_workspace,
    get_session,
    require_authenticated_session,
)
from app.api.routes.auth import _session_response, _set_session_cookie
from app.core.config import Settings
from app.models.auth import SecurityAuditEvent, TelegramIdentity
from app.models.account import Account
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership
from app.schemas.auth import AuthSessionResponse
from app.schemas.telegram import TelegramLinkCodeResponse, TelegramMiniAppSessionRequest, TelegramStatusResponse
from app.services.telegram_service import TelegramInitDataError, issue_link_code, validate_init_data

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatusResponse)
async def telegram_status(
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> TelegramStatusResponse:
    identity = (
        await session.execute(select(TelegramIdentity).where(TelegramIdentity.user_id == authenticated.user.id))
    ).scalar_one_or_none()
    workspace = await session.get(Workspace, identity.default_workspace_id) if identity else None
    account = None
    if identity is not None and identity.default_account_id is not None:
        account = await session.get(Account, identity.default_account_id)
        # A stale pointer into another space is never shown as the target.
        if account is None or account.workspace_id != identity.default_workspace_id or account.is_archived:
            account = None
    return TelegramStatusResponse(
        configured=bool(settings.telegram_bot_token.get_secret_value()),
        mini_app_configured=settings.telegram_mini_app_enabled,
        linked=identity is not None,
        username=identity.telegram_username if identity else None,
        workspace_name=workspace.display_name if workspace else None,
        account_name=account.name if account else None,
        account_currency=account.currency if account else None,
    )


@router.post("/link-code", response_model=TelegramLinkCodeResponse)
async def create_telegram_link_code(
    context: RequestWorkspace = Depends(get_request_workspace),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> TelegramLinkCodeResponse:
    context.require_mutation()
    if context.user is None or context.workspace_id is None:
        raise HTTPException(status_code=503, detail="Application authentication is required")
    if not settings.telegram_bot_token.get_secret_value():
        raise HTTPException(status_code=503, detail="Telegram is not configured")
    lifetime = timedelta(seconds=settings.telegram_link_code_ttl_seconds)
    code = await issue_link_code(
        session,
        user_id=context.user.id,
        workspace_id=context.workspace_id,
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        lifetime=lifetime,
    )
    session.add(
        SecurityAuditEvent(
            actor_user_id=context.user.id,
            workspace_id=context.workspace_id,
            event_type="telegram_link_code_issued",
            outcome="success",
        )
    )
    await session.commit()
    return TelegramLinkCodeResponse(code=code, expires_in_seconds=int(lifetime.total_seconds()))


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(
    authenticated: AuthenticatedSession = Depends(require_authenticated_session),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(
        delete(TelegramIdentity).where(TelegramIdentity.user_id == authenticated.user.id)
    )
    session.add(
        SecurityAuditEvent(
            actor_user_id=authenticated.user.id,
            event_type="telegram_unlinked",
            outcome="success" if result.rowcount else "not_linked",
        )
    )
    await session.commit()


@router.post("/session", response_model=AuthSessionResponse)
async def create_telegram_session(
    payload: TelegramMiniAppSessionRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    if not settings.app_auth_required or not credential_transport_allowed(request, settings):
        raise HTTPException(status_code=404, detail="Authentication is not available")
    try:
        telegram_user = validate_init_data(
            payload.init_data,
            bot_token=settings.telegram_bot_token.get_secret_value(),
            max_age=timedelta(seconds=settings.telegram_init_data_max_age_seconds),
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail="Unable to sign in with Telegram") from exc
    identity = (
        await session.execute(
            select(TelegramIdentity, User)
            .join(User, User.id == TelegramIdentity.user_id)
            .where(
                TelegramIdentity.telegram_user_id == telegram_user["id"],
                User.status == UserStatus.ACTIVE,
            )
        )
    ).one_or_none()
    if identity is None:
        raise HTTPException(status_code=403, detail="Telegram account is not linked")
    telegram_identity, user = identity
    membership = (
        await session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.workspace_id == telegram_identity.default_workspace_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Telegram workspace is no longer available")
    service = auth_session_service(settings)
    current = None
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    if current_token:
        current = await service.resolve(session, token=current_token, refresh_idle=False)
    issued = await service.rotate(
        session,
        current=current,
        user_id=user.id,
        client_ip=client_signal(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    telegram_identity.last_authenticated_at = datetime.now(UTC)
    session.add(
        SecurityAuditEvent(
            actor_user_id=user.id,
            workspace_id=telegram_identity.default_workspace_id,
            event_type="telegram_login",
            outcome="success",
        )
    )
    result = await _session_response(
        session,
        user=user,
        csrf_token=issued.csrf_token,
        requested_workspace=str(telegram_identity.default_workspace_id),
    )
    await session.commit()
    _set_session_cookie(response, request, settings, issued.session_token)
    return result
