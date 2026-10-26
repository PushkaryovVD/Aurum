"""Password recovery by e-mail.

Two public endpoints, both behind the same-origin / transport checks and a
dedicated rate limiter:

* `POST /auth/password-reset/request` always answers 202 with the same body,
  whether or not the login exists, so it cannot be used to discover accounts.
  The e-mail is sent after the response (BackgroundTasks), which also keeps
  response timing independent of the account's existence.
* `POST /auth/password-reset/confirm` sets the new password, signs the user
  out everywhere and invalidates the link (see password_reset_service).
"""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_signal, credential_transport_allowed, get_app_settings, get_session, request_origin
from app.api.routes.auth import password_context, read_auth_json
from app.core.config import Settings
from app.core.identity import is_safe_text, normalize_identifier, valid_normalized_identifier
from app.models.auth import SecurityAuditEvent
from app.security.auth import validate_same_origin
from app.services.auth_rate_limit_service import AuthRateLimiter
from app.services.email_service import (
    PasswordResetEmail,
    looks_like_email,
    password_reset_link,
    send_password_reset_email,
)
from app.services.password_reset_service import (
    find_active_user,
    issue_reset_token,
    resolve_reset_token,
    revoke_all_sessions,
)

router = APIRouter(prefix="/auth/password-reset", tags=["authentication"])

GENERIC_REQUEST_REPLY = {"detail": "If the account exists and has an e-mail login, a reset link has been sent"}
GENERIC_CONFIRM_ERROR = "Password reset link is not valid"


def password_reset_rate_limiter(settings: Settings) -> AuthRateLimiter:
    return AuthRateLimiter(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        max_attempts=settings.auth_login_max_attempts,
        window=timedelta(seconds=settings.auth_login_window_seconds),
        block_for=timedelta(seconds=settings.auth_login_block_seconds),
        purpose="password-reset",
    )


def _available(settings: Settings) -> bool:
    return settings.app_auth_required and settings.smtp_enabled


def _trusted_request(request: Request, settings: Settings) -> bool:
    same_origin = validate_same_origin(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        expected_origin=request_origin(request, settings),
    )
    return same_origin and credential_transport_allowed(request, settings)


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, str]:
    if not _available(settings):
        raise HTTPException(status_code=503, detail="Password reset is not available")
    if not _trusted_request(request, settings):
        raise HTTPException(status_code=404, detail="Password reset is not available")

    raw_payload = await read_auth_json(request)
    raw_identifier = raw_payload.get("identifier") if raw_payload is not None else None
    identifier = valid_normalized_identifier(raw_identifier) if isinstance(raw_identifier, str) else None
    signal = client_signal(request, settings)
    limiter = password_reset_rate_limiter(settings)
    allowed, limit_state = await limiter.check_scoped(
        session,
        credential=normalize_identifier(raw_identifier) if isinstance(raw_identifier, str) else "",
        client_signal=signal,
    )
    if not allowed:
        session.add(SecurityAuditEvent(event_type="password_reset_requested", outcome="rate_limited"))
        await session.commit()
        raise HTTPException(status_code=429, detail="Too many password reset requests")
    # Every request counts towards the limit, so it also caps outgoing mail.
    limiter.record_scoped_failure(session, state=limit_state)

    user = await find_active_user(session, identifier) if identifier else None
    if user is not None and looks_like_email(user.normalized_login):
        token, expires_at = issue_reset_token(
            settings.auth_hmac_secret.get_secret_value(),
            user,
            ttl=timedelta(seconds=settings.auth_password_reset_ttl_seconds),
        )
        base_url = settings.public_url.strip() or request_origin(request, settings)
        background.add_task(
            send_password_reset_email,
            settings,
            PasswordResetEmail(
                recipient=user.normalized_login,
                display_name=user.display_name,
                link=password_reset_link(base_url, token),
                expires_at=expires_at,
            ),
        )
        session.add(SecurityAuditEvent(actor_user_id=user.id, event_type="password_reset_requested", outcome="success"))
    else:
        session.add(SecurityAuditEvent(event_type="password_reset_requested", outcome="failure"))
    await session.commit()
    return GENERIC_REQUEST_REPLY


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    if not _available(settings):
        raise HTTPException(status_code=503, detail="Password reset is not available")
    if not _trusted_request(request, settings):
        raise HTTPException(status_code=404, detail="Password reset is not available")

    raw_payload = await read_auth_json(request)
    raw_token = raw_payload.get("token") if raw_payload is not None else None
    raw_password = raw_payload.get("password") if raw_payload is not None else None
    token = raw_token if isinstance(raw_token, str) else ""
    signal = client_signal(request, settings)
    limiter = password_reset_rate_limiter(settings)
    allowed, limit_state = await limiter.check_scoped(session, credential=f"confirm:{token}", client_signal=signal)
    if not allowed:
        session.add(SecurityAuditEvent(event_type="password_reset", outcome="rate_limited"))
        await session.commit()
        raise HTTPException(status_code=429, detail="Too many password reset attempts")

    password_ok = isinstance(raw_password, str) and is_safe_text(raw_password, min_length=12, max_length=1024)
    user = await resolve_reset_token(session, settings.auth_hmac_secret.get_secret_value(), token)
    if user is None or not password_ok:
        limiter.record_scoped_failure(session, state=limit_state)
        session.add(SecurityAuditEvent(event_type="password_reset", outcome="failure"))
        await session.commit()
        # 422 only for a password that breaks the policy on an otherwise valid link.
        if user is not None:
            raise HTTPException(status_code=422, detail="Password must be at least 12 characters")
        raise HTTPException(status_code=400, detail=GENERIC_CONFIRM_ERROR)

    password_service, _ = password_context(settings)
    assert isinstance(raw_password, str)
    # Changing the hash also invalidates this and every other reset link.
    user.password_hash = password_service.hash(raw_password)
    await revoke_all_sessions(session, user.id)
    await limiter.reset_scoped(session, state=limit_state)
    session.add(SecurityAuditEvent(actor_user_id=user.id, event_type="password_reset", outcome="success"))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
