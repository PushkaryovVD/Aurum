"""Stateless password-reset tokens.

A token is `<payload>.<signature>` where the payload carries the user id and
an expiry time, and the signature is an HMAC over that payload *and the
user's current password hash*. No database row is needed:

* it expires on its own;
* it becomes invalid the moment the password changes, so it is effectively
  single-use (the same approach as Django's PasswordResetTokenGenerator);
* disabling the account invalidates it as well.

The raw token only ever travels in the e-mailed link's URL fragment, which
browsers do not send to the server or to proxy logs.
"""
import base64
import hashlib
import hmac
import struct
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import UserSession
from app.models.workspace import User, UserStatus

_PURPOSE = b"aurum-password-reset-v1"
_PAYLOAD = struct.Struct(">16sQ")  # user id bytes, expiry as unix seconds


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes | None:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        return None


def _signature(secret: str, payload: bytes, user: User) -> bytes:
    material = b"\0".join(
        (_PURPOSE, payload, user.password_hash.encode("utf-8"), user.status.value.encode("ascii"))
    )
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).digest()


def issue_reset_token(secret: str, user: User, *, ttl: timedelta, now: datetime | None = None) -> tuple[str, datetime]:
    if not secret:
        raise ValueError("password reset requires the auth HMAC secret")
    expires_at = (now or datetime.now(UTC)) + ttl
    payload = _PAYLOAD.pack(user.id.bytes, int(expires_at.timestamp()))
    return f"{_b64encode(payload)}.{_b64encode(_signature(secret, payload, user))}", expires_at


async def resolve_reset_token(
    session: AsyncSession, secret: str, token: str, *, now: datetime | None = None
) -> User | None:
    """Return the user the token was issued for, or None for any invalid,
    expired, already-used or tampered token (deliberately indistinguishable)."""
    if not secret or not token or len(token) > 256 or token.count(".") != 1:
        return None
    encoded_payload, encoded_signature = token.split(".")
    payload = _b64decode(encoded_payload)
    signature = _b64decode(encoded_signature)
    if payload is None or signature is None or len(payload) != _PAYLOAD.size:
        return None
    user_bytes, expires_ts = _PAYLOAD.unpack(payload)
    if expires_ts < int((now or datetime.now(UTC)).timestamp()):
        return None
    user = await session.get(User, UUID(bytes=user_bytes))
    if user is None or user.status != UserStatus.ACTIVE:
        return None
    if not hmac.compare_digest(signature, _signature(secret, payload, user)):
        return None
    return user


async def find_active_user(session: AsyncSession, normalized_login: str) -> User | None:
    user = (await session.execute(select(User).where(User.normalized_login == normalized_login))).scalar_one_or_none()
    return user if user is not None and user.status == UserStatus.ACTIVE else None


async def revoke_all_sessions(session: AsyncSession, user_id: UUID, *, now: datetime | None = None) -> None:
    """A password reset signs the account out everywhere."""
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now or datetime.now(UTC))
    )
