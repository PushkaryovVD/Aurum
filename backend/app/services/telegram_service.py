"""Telegram Mini App validation and single-use account-link capabilities."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets
from urllib.parse import parse_qsl
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import TelegramIdentity, TelegramLinkCode
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership, WorkspaceStatus
from app.security.auth import capability_hmac


class TelegramInitDataError(ValueError):
    pass


def validate_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age: timedelta,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate Telegram.WebApp.initData using Telegram's documented HMAC scheme."""
    if not bot_token:
        raise TelegramInitDataError("Telegram is not configured")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise TelegramInitDataError("Invalid Telegram data") from exc
    if len({key for key, _ in pairs}) != len(pairs):
        raise TelegramInitDataError("Duplicate Telegram fields")
    values = dict(pairs)
    supplied_hash = values.pop("hash", "")
    if len(supplied_hash) != 64:
        raise TelegramInitDataError("Invalid Telegram signature")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_hash, expected_hash):
        raise TelegramInitDataError("Invalid Telegram signature")
    try:
        auth_date = datetime.fromtimestamp(int(values["auth_date"]), tz=UTC)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise TelegramInitDataError("Invalid Telegram timestamp") from exc
    checked_at = now or datetime.now(UTC)
    if auth_date > checked_at + timedelta(seconds=30) or checked_at - auth_date > max_age:
        raise TelegramInitDataError("Telegram data expired")
    try:
        user = json.loads(values["user"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramInitDataError("Telegram user is missing") from exc
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise TelegramInitDataError("Telegram user is invalid")
    return user


async def issue_link_code(
    session: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID,
    hmac_secret: str,
    lifetime: timedelta,
) -> str:
    now = datetime.now(UTC)
    await session.execute(
        delete(TelegramLinkCode).where(
            TelegramLinkCode.user_id == user_id,
            TelegramLinkCode.consumed_at.is_(None),
        )
    )
    # Avoid ambiguous glyphs when the code is typed on a phone.
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    session.add(
        TelegramLinkCode(
            user_id=user_id,
            workspace_id=workspace_id,
            code_hmac=capability_hmac(hmac_secret, f"telegram-link\0{code}"),
            issued_at=now,
            expires_at=now + lifetime,
        )
    )
    await session.flush()
    return code


async def consume_link_code(
    session: AsyncSession,
    *,
    code: str,
    telegram_user_id: int,
    telegram_username: str | None,
    hmac_secret: str,
) -> TelegramIdentity | None:
    now = datetime.now(UTC)
    code_hmac = capability_hmac(hmac_secret, f"telegram-link\0{code.strip().upper()}")
    record = (
        await session.execute(
            select(TelegramLinkCode)
            .where(
                TelegramLinkCode.code_hmac == code_hmac,
                TelegramLinkCode.consumed_at.is_(None),
                TelegramLinkCode.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if record is None:
        return None
    membership = (
        await session.execute(
            select(WorkspaceMembership)
            .join(User, User.id == WorkspaceMembership.user_id)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id == record.user_id,
                WorkspaceMembership.workspace_id == record.workspace_id,
                WorkspaceMembership.revoked_at.is_(None),
                User.status == UserStatus.ACTIVE,
                Workspace.status == WorkspaceStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        return None
    # A Telegram account and an Aurum account are both one-to-one. Relinking
    # explicitly replaces either older association instead of leaving aliases.
    await session.execute(
        delete(TelegramIdentity).where(
            (TelegramIdentity.user_id == record.user_id)
            | (TelegramIdentity.telegram_user_id == telegram_user_id)
        )
    )
    identity = TelegramIdentity(
        user_id=record.user_id,
        default_workspace_id=record.workspace_id,
        telegram_user_id=telegram_user_id,
        telegram_username=(telegram_username[:64] if telegram_username else None),
    )
    session.add(identity)
    record.consumed_at = now
    await session.flush()
    return identity
