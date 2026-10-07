from collections.abc import AsyncGenerator
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db
from app.models.auth import UserSession
from app.models.workspace import User, Workspace, WorkspaceMembership, WorkspaceRole
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


@dataclass(frozen=True, slots=True)
class RequestWorkspace:
    """Server-authorized financial scope for one request.

    ``workspace_id`` is intentionally nullable only while application auth is
    disabled, preserving the original installation-wide behavior.
    """

    user: User | None
    workspace: Workspace | None
    membership: WorkspaceMembership | None

    @property
    def workspace_id(self) -> UUID | None:
        return self.workspace.id if self.workspace is not None else None

    @property
    def author_user_id(self) -> UUID | None:
        return self.user.id if self.user is not None else None

    def require_mutation(self) -> None:
        if self.membership is not None and self.membership.role == WorkspaceRole.VIEWER:
            raise HTTPException(status_code=403, detail="Editor or owner role required")


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def auth_session_service(settings: Settings) -> AuthSessionService:
    return AuthSessionService(
        hmac_secret=settings.auth_hmac_secret.get_secret_value(),
        idle_lifetime=settings.auth_session_idle_lifetime,
        absolute_lifetime=settings.auth_session_absolute_lifetime,
    )


def _peer_address(request: Request):
    if request.client is None:
        return None
    try:
        return ip_address(request.client.host)
    except ValueError:
        return None


def _trusted_proxy_peer(request: Request, settings: Settings) -> bool:
    peer = _peer_address(request)
    if peer is None:
        return False
    return _address_in_cidrs(peer, settings.auth_trusted_proxy_cidrs_list)


def _address_in_cidrs(address, cidrs: list[str]) -> bool:
    return any(address in ip_network(cidr, strict=False) for cidr in cidrs)


def request_scheme(request: Request, settings: Settings) -> str:
    if _trusted_proxy_peer(request, settings):
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        if forwarded in {"http", "https"}:
            return forwarded
    return request.url.scheme


def request_origin(request: Request, settings: Settings) -> str:
    scheme = request_scheme(request, settings)
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}"


def client_signal(request: Request, settings: Settings) -> str:
    if _trusted_proxy_peer(request, settings):
        forwarded = request.headers.get("x-real-ip")
        if forwarded:
            try:
                return str(ip_address(forwarded.strip()))
            except ValueError:
                pass
    peer = _peer_address(request)
    return str(peer) if peer is not None else "unknown"


def credential_transport_allowed(request: Request, settings: Settings) -> bool:
    if request_scheme(request, settings) == "https":
        return True
    try:
        client = ip_address(client_signal(request, settings))
    except ValueError:
        return False
    return settings.environment != "production" and _address_in_cidrs(
        client, settings.auth_loopback_client_cidrs_list
    )


def finance_access_ready(settings: Settings) -> bool:
    """Legacy unauthenticated mode remains usable until scoped finance activation."""
    return not settings.app_auth_required


async def resolve_authenticated_session(
    request: Request,
    session: AsyncSession,
    settings: Settings,
) -> AuthenticatedSession:
    if not settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Application authentication is not enabled")
    if not credential_transport_allowed(request, settings):
        raise HTTPException(status_code=404, detail="Authentication is not available")

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
        expected_origin=request_origin(request, settings),
    )
    return AuthenticatedSession(record=record, user=user, token=token)


async def require_authenticated_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthenticatedSession:
    authenticated = await resolve_authenticated_session(request, session, settings)
    await session.commit()
    return authenticated


async def require_finance_access(
    settings: Settings = Depends(get_app_settings),
) -> None:
    if not finance_access_ready(settings):
        raise HTTPException(status_code=503, detail="Financial access is not ready")


async def get_request_workspace(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> RequestWorkspace:
    if not settings.app_auth_required:
        return RequestWorkspace(user=None, workspace=None, membership=None)

    authenticated = await require_authenticated_session(request, session, settings)
    selected = request.headers.get("X-Aurum-Workspace")
    if selected is None:
        workspace_id = authenticated.user.personal_workspace_id
    else:
        try:
            workspace_id = UUID(selected)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Workspace not found") from exc

    row = (
        await session.execute(
            select(WorkspaceMembership, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == authenticated.user.id,
                WorkspaceMembership.revoked_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    membership, workspace = row
    return RequestWorkspace(user=authenticated.user, workspace=workspace, membership=membership)
