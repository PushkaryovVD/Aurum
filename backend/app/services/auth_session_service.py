"""Opaque server-side session issuance and lifecycle management."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import UserSession
from app.models.workspace import User, UserStatus
from app.security.auth import capability_hmac, csrf_token_matches


@dataclass(frozen=True, slots=True)
class IssuedSession:
    record: UserSession
    session_token: str
    csrf_token: str


class AuthSessionService:
    def __init__(self, *, hmac_secret: str, idle_lifetime: timedelta, absolute_lifetime: timedelta) -> None:
        if not hmac_secret:
            raise ValueError("HMAC secret must not be empty")
        if idle_lifetime <= timedelta(0) or absolute_lifetime <= timedelta(0):
            raise ValueError("session lifetimes must be positive")
        if idle_lifetime > absolute_lifetime:
            raise ValueError("idle lifetime must not exceed absolute lifetime")
        self._hmac_secret = hmac_secret
        self._idle_lifetime = idle_lifetime
        self._absolute_lifetime = absolute_lifetime

    async def issue(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        now: datetime | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedSession:
        issued_at = now or datetime.now(UTC)
        session_token = secrets.token_urlsafe(32)
        csrf_token = self.csrf_token_for_session(session_token)
        record = UserSession(
            user_id=user_id,
            token_hmac=capability_hmac(self._hmac_secret, session_token),
            csrf_secret=capability_hmac(self._hmac_secret, csrf_token),
            last_seen_at=issued_at,
            idle_expires_at=issued_at + self._idle_lifetime,
            absolute_expires_at=issued_at + self._absolute_lifetime,
            client_ip_hmac=(capability_hmac(self._hmac_secret, client_ip) if client_ip else None),
            user_agent_hmac=(capability_hmac(self._hmac_secret, user_agent) if user_agent else None),
        )
        session.add(record)
        await session.flush()
        return IssuedSession(record=record, session_token=session_token, csrf_token=csrf_token)

    def csrf_token_for_session(self, session_token: str) -> str:
        """Derive a stable token without storing a recoverable CSRF secret."""
        return capability_hmac(self._hmac_secret, f"csrf\0{session_token}").hex()

    async def resolve(
        self,
        session: AsyncSession,
        *,
        token: str,
        now: datetime | None = None,
        refresh_idle: bool = True,
    ) -> UserSession | None:
        checked_at = now or datetime.now(UTC)
        token_hmac = capability_hmac(self._hmac_secret, token)
        statement = (
            select(UserSession)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hmac == token_hmac,
                UserSession.revoked_at.is_(None),
                UserSession.idle_expires_at > checked_at,
                UserSession.absolute_expires_at > checked_at,
                User.status == UserStatus.ACTIVE,
            )
        )
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            return None
        if refresh_idle:
            record.last_seen_at = checked_at
            record.idle_expires_at = min(checked_at + self._idle_lifetime, record.absolute_expires_at)
            await session.flush()
        return record

    def revoke(self, record: UserSession, *, now: datetime | None = None) -> None:
        if record.revoked_at is None:
            record.revoked_at = now or datetime.now(UTC)

    async def rotate(
        self,
        session: AsyncSession,
        *,
        current: UserSession | None,
        user_id: UUID,
        now: datetime | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedSession:
        rotated_at = now or datetime.now(UTC)
        if current is not None:
            self.revoke(current, now=rotated_at)
        return await self.issue(
            session,
            user_id=user_id,
            now=rotated_at,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    def verify_csrf(self, record: UserSession, token: str) -> bool:
        return csrf_token_matches(record.csrf_secret, token, self._hmac_secret)
