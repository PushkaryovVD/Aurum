from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db
from app.models.auth import UserSession
from app.models.workspace import User
from app.security.auth import enforce_csrf
from app.services.auth_session_service import AuthSessionService

DbSession = AsyncSession
SESSION_COOKIE_NAME = "aurum_session"
CSRF_HEADER_NAME = "X-CSRF-Token"


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    record: UserSession
    user: User
    token: str


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def auth_session_service(settings: Settings) -> AuthSessionService:
    return AuthSessionService(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        idle_lifetime=settings.auth_session_idle_lifetime,
        absolute_lifetime=settings.auth_session_absolute_lifetime,
    )


def request_origin(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}"


def client_signal(request: Request) -> str:
    # nginx overwrites X-Real-IP before proxying; direct development requests
    # fall back to the ASGI peer address.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


async def require_authenticated_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthenticatedSession:
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    service = auth_session_service(settings)
    record = await service.resolve(session, token=token)
    if record is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = await session.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    enforce_csrf(
        request,
        record,
        csrf_token=request.headers.get(CSRF_HEADER_NAME),
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        expected_origin=request_origin(request),
    )
    await session.commit()
    return AuthenticatedSession(record=record, user=user, token=token)


async def require_app_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> None:
    if settings.app_auth_required:
        await require_authenticated_session(request, session, settings)
