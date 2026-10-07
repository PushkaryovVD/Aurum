"""Application session login, logout, and current-user endpoints."""
from collections.abc import Mapping
from datetime import timedelta
from functools import lru_cache
import json
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
    credential_transport_allowed,
    finance_access_ready,
    get_app_settings,
    get_session,
    request_origin,
    require_authenticated_session,
)
from app.core.config import Settings
from app.core.identity import (
    is_safe_text,
    normalize_identifier,
    valid_display_name,
    valid_normalized_identifier,
)
from app.models.auth import SecurityAuditEvent
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership
from app.schemas.auth import (
    AuthSessionResponse,
    AuthenticatedUser,
    FirstOwnerBootstrapRequest,
    LoginRequest,
    WorkspaceSummary,
)
from app.schemas.workspace import NewAccountInvitationAccept
from app.security.auth import PasswordService, validate_same_origin
from app.services.auth_rate_limit_service import AuthRateLimiter
from app.services.workspace_service import (
    FirstOwnerBootstrapUnavailable,
    InvitationUnavailable,
    bootstrap_first_owner,
    bootstrap_invited_user,
    initial_owner_bootstrap_available,
    initial_owner_bootstrap_required,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
GENERIC_LOGIN_ERROR = "Unable to sign in"
ACTIVE_WORKSPACE_HEADER = "X-Aurum-Workspace"
MAX_AUTH_REQUEST_BODY_BYTES = 16 * 1024


@router.get("/status")
async def read_auth_status(
    response: Response,
    settings: Settings = Depends(get_app_settings),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool | str]:
    """Public mode only; financial isolation and operator bootstrap are incomplete."""
    response.headers["Cache-Control"] = "no-store"
    return {
        "app_auth_required": settings.app_auth_required,
        "finance_access_ready": finance_access_ready(settings),
        "session_transport": "https" if settings.environment == "production" else "https_or_loopback",
        "initial_owner_bootstrap_required": await initial_owner_bootstrap_required(
            session, app_auth_required=settings.app_auth_required
        ),
        "initial_owner_bootstrap_available": await initial_owner_bootstrap_available(
            session, app_auth_required=settings.app_auth_required
        ),
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


def first_owner_rate_limiter(settings: Settings) -> AuthRateLimiter:
    return AuthRateLimiter(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        max_attempts=settings.auth_login_max_attempts,
        window=timedelta(seconds=settings.auth_login_window_seconds),
        block_for=timedelta(seconds=settings.auth_login_block_seconds),
        purpose="first-owner-bootstrap",
    )


def parse_first_owner_payload(raw_payload: Mapping[str, object]) -> FirstOwnerBootstrapRequest | None:
    """Keep malformed bootstrap attempts inside the generic, rate-limited path."""
    bootstrap_code = raw_payload.get("bootstrap_code")
    identifier = raw_payload.get("identifier")
    display_name = raw_payload.get("display_name")
    password = raw_payload.get("password")
    if not isinstance(bootstrap_code, str):
        return None
    if not isinstance(identifier, str):
        return None
    if not isinstance(display_name, str):
        return None
    if not isinstance(password, str):
        return None
    if not (
        is_safe_text(bootstrap_code, min_length=1, max_length=1024)
        and valid_normalized_identifier(identifier) is not None
        and len(identifier) <= 320
        and valid_display_name(display_name) is not None
        and is_safe_text(password, min_length=12, max_length=1024)
    ):
        return None
    return FirstOwnerBootstrapRequest(
        bootstrap_code=bootstrap_code,
        identifier=identifier,
        display_name=display_name,
        password=password,
    )


def parse_login_payload(raw_payload: Mapping[str, object]) -> LoginRequest | None:
    """Validate login text without exposing detailed schema errors."""
    identifier = raw_payload.get("identifier")
    password = raw_payload.get("password")
    if not isinstance(identifier, str) or not isinstance(password, str):
        return None
    if not (
        len(identifier) <= 320
        and valid_normalized_identifier(identifier) is not None
        and is_safe_text(password, min_length=1, max_length=1024)
    ):
        return None
    return LoginRequest(identifier=identifier, password=password)


def parse_invitation_accept_payload(
    raw_payload: Mapping[str, object],
) -> NewAccountInvitationAccept | None:
    """Keep malformed invitation attempts inside the generic limiter path."""
    token = raw_payload.get("token")
    identifier = raw_payload.get("identifier")
    display_name = raw_payload.get("display_name")
    password = raw_payload.get("password")
    if not all(isinstance(value, str) for value in (token, identifier, display_name, password)):
        return None
    assert isinstance(token, str)
    assert isinstance(identifier, str)
    assert isinstance(display_name, str)
    assert isinstance(password, str)
    if not (
        is_safe_text(token, min_length=1, max_length=1024)
        and valid_normalized_identifier(identifier) is not None
        and len(identifier) <= 320
        and valid_display_name(display_name) is not None
        and is_safe_text(password, min_length=12, max_length=1024)
    ):
        return None
    return NewAccountInvitationAccept(
        token=token,
        identifier=identifier,
        display_name=display_name,
        password=password,
    )


def parse_invitation_token(raw_payload: Mapping[str, object]) -> str | None:
    token = raw_payload.get("token")
    if not isinstance(token, str) or not is_safe_text(token, min_length=1, max_length=1024):
        return None
    return token


async def read_auth_json(request: Request) -> Mapping[str, object] | None:
    """Read a small JSON object while keeping parse failures non-disclosing."""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return None
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
            if parsed_length < 0 or parsed_length > MAX_AUTH_REQUEST_BODY_BYTES:
                return None
        except ValueError:
            return None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_AUTH_REQUEST_BODY_BYTES:
            return None
        body.extend(chunk)
    try:
        decoded = bytes(body).decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _cookie_secure(request: Request, settings: Settings) -> bool:
    return settings.environment == "production" or request_origin(request, settings).startswith("https://")


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
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")
    limiter = rate_limiter(settings)
    signal = client_signal(request, settings)
    same_origin = validate_same_origin(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        expected_origin=request_origin(request, settings),
    )
    if not credential_transport_allowed(request, settings) or not same_origin:
        allowed, limit_state = await limiter.check_scoped(
            session,
            credential=f"transport:{signal}",
            client_signal=signal,
        )
        if allowed:
            limiter.record_scoped_failure(session, state=limit_state)
        session.add(
            SecurityAuditEvent(
                event_type="login",
                outcome="failure" if allowed else "rate_limited",
            )
        )
        await session.commit()
        raise HTTPException(status_code=404, detail="Authentication is not available")

    raw_payload = await read_auth_json(request)
    raw_identifier = raw_payload.get("identifier") if raw_payload is not None else None
    credential = normalize_identifier(raw_identifier) if isinstance(raw_identifier, str) else ""
    allowed, limit_state = await limiter.check_scoped(
        session,
        credential=credential,
        client_signal=signal,
    )
    if not allowed:
        session.add(SecurityAuditEvent(event_type="login", outcome="rate_limited"))
        await session.commit()
        raise HTTPException(status_code=429, detail=GENERIC_LOGIN_ERROR)

    payload = parse_login_payload(raw_payload) if raw_payload is not None else None
    if payload is None:
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="login", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    identifier = valid_normalized_identifier(payload.identifier)
    assert identifier is not None

    user = (
        await session.execute(select(User).where(User.normalized_login == identifier))
    ).scalar_one_or_none()
    password_service, dummy_hash = password_context(settings)
    encoded_hash = user.password_hash if user is not None else dummy_hash
    password_valid = password_service.verify(encoded_hash, payload.password)
    if user is None or user.status != UserStatus.ACTIVE or not password_valid:
        limiter.record_scoped_failure(session, state=limit_state)
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
        client_ip=client_signal(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset_scoped(session, state=limit_state)
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


@router.post("/bootstrap/initial-owner", response_model=AuthSessionResponse)
async def bootstrap_initial_owner(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Consume the pending operator code and create one personal owner."""
    if not settings.app_auth_required:
        raise HTTPException(status_code=404, detail="Initial owner setup is not available")
    limiter = first_owner_rate_limiter(settings)
    signal = client_signal(request, settings)
    origin = request_origin(request, settings)
    transport_allowed = credential_transport_allowed(request, settings)
    same_origin = validate_same_origin(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        expected_origin=origin,
    )
    hmac_secret = settings.auth_hmac_secret.get_secret_value()
    if not transport_allowed or not same_origin or len(hmac_secret.encode("utf-8")) < 32:
        allowed, limit_state = await limiter.check_scoped(
            session,
            credential=f"transport:{signal}",
            client_signal=signal,
        )
        if allowed:
            limiter.record_scoped_failure(session, state=limit_state)
        session.add(
            SecurityAuditEvent(
                event_type="initial_owner_bootstrap",
                outcome="failure" if allowed else "rate_limited",
            )
        )
        await session.commit()
        raise HTTPException(status_code=404, detail="Initial owner setup is not available")
    allowed, limit_state = await limiter.check_scoped(
        session,
        credential="initial-owner",
        client_signal=signal,
    )
    if not allowed:
        session.add(
            SecurityAuditEvent(event_type="initial_owner_bootstrap", outcome="rate_limited")
        )
        await session.commit()
        raise HTTPException(status_code=429, detail="Initial owner setup is not available")
    raw_payload = await read_auth_json(request)
    payload = parse_first_owner_payload(raw_payload) if raw_payload is not None else None
    if payload is None:
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="initial_owner_bootstrap", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=404, detail="Initial owner setup is not available")
    password_service, _ = password_context(settings)
    try:
        user = await bootstrap_first_owner(
            session,
            raw_code=payload.bootstrap_code,
            identifier=payload.identifier,
            display_name=payload.display_name,
            password_hash=password_service.hash(payload.password),
            default_currency=settings.default_currency,
            hmac_secret=hmac_secret,
        )
    except (FirstOwnerBootstrapUnavailable, IntegrityError) as exc:
        await session.rollback()
        _, limit_state = await limiter.check_scoped(
            session,
            credential="initial-owner",
            client_signal=signal,
        )
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="initial_owner_bootstrap", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=404, detail="Initial owner setup is not available") from exc
    issued = await auth_session_service(settings).issue(
        session,
        user_id=user.id,
        client_ip=client_signal(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset_scoped(session, state=limit_state)
    session.add(SecurityAuditEvent(actor_user_id=user.id, workspace_id=user.personal_workspace_id, event_type="initial_owner_bootstrap", outcome="success"))
    result = await _session_response(
        session,
        user=user,
        csrf_token=issued.csrf_token,
        requested_workspace=None,
    )
    await session.commit()
    _set_session_cookie(response, request, settings, issued.session_token)
    return result


@router.post("/invitations/accept", response_model=AuthSessionResponse)
async def accept_new_account_invitation(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Consume an invitation only as part of its explicit account-creation flow."""
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")
    limiter = invitation_rate_limiter(settings)
    signal = client_signal(request, settings)
    same_origin = validate_same_origin(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        expected_origin=request_origin(request, settings),
    )
    if not credential_transport_allowed(request, settings) or not same_origin:
        allowed, limit_state = await limiter.check_scoped(
            session,
            credential=f"transport:{signal}",
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
        raise HTTPException(status_code=404, detail="Invitation is not available")

    raw_payload = await read_auth_json(request)
    payload = parse_invitation_accept_payload(raw_payload) if raw_payload is not None else None
    raw_token = raw_payload.get("token") if raw_payload is not None else None
    token = raw_token if isinstance(raw_token, str) else ""
    allowed, limit_state = await limiter.check_scoped(
        session,
        credential=token,
        client_signal=signal,
    )
    if not allowed:
        session.add(SecurityAuditEvent(event_type="invitation_accepted", outcome="rate_limited"))
        await session.commit()
        raise HTTPException(status_code=429, detail="Invitation is not available")

    if payload is None:
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="invitation_accepted", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=404, detail="Invitation is not available")

    normalized_identifier = valid_normalized_identifier(payload.identifier)
    display_name = valid_display_name(payload.display_name)
    assert normalized_identifier is not None
    assert display_name is not None

    password_service, _ = password_context(settings)
    try:
        user, invitation = await bootstrap_invited_user(
            session,
            raw_token=payload.token,
            identifier=normalized_identifier,
            display_name=display_name,
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
            _, limit_state = await limiter.check_scoped(
                session,
                credential=payload.token,
                client_signal=signal,
            )
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="invitation_accepted", outcome="failure"))
        await session.commit()
        raise HTTPException(status_code=404, detail="Invitation is not available") from exc

    issued = await auth_session_service(settings).issue(
        session,
        user_id=user.id,
        client_ip=client_signal(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    await limiter.reset_scoped(session, state=limit_state)
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
