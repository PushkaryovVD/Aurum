"""Database-backed, privacy-minimized authentication rate limiting."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import AuthRateLimit
from app.security.auth import capability_hmac


class AuthRateLimiter:
    """Fixed-window limiter serialized by a transaction-scoped advisory lock."""

    def __init__(
        self,
        *,
        hmac_secret: str,
        max_attempts: int,
        window: timedelta,
        block_for: timedelta,
        purpose: str = "login",
    ) -> None:
        if max_attempts < 1 or window <= timedelta(0) or block_for <= timedelta(0):
            raise ValueError("rate-limit settings must be positive")
        self._hmac_secret = hmac_secret
        self._max_attempts = max_attempts
        self._window = window
        self._block_for = block_for
        self._purpose = purpose

    def bucket_hmac(self, *, identifier: str, client_signal: str) -> bytes:
        return capability_hmac(
            self._hmac_secret,
            f"{self._purpose}\0{identifier}\0{client_signal}",
        )

    async def lock_and_get(
        self,
        session: AsyncSession,
        *,
        bucket_hmac: bytes,
    ) -> AuthRateLimit | None:
        # PostgreSQL advisory locks avoid a first-use race before a bucket row
        # exists. The bucket itself remains an opaque HMAC in both places.
        lock_key = int.from_bytes(bucket_hmac[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        statement = select(AuthRateLimit).where(
            AuthRateLimit.purpose == self._purpose,
            AuthRateLimit.bucket_hmac == bucket_hmac,
        )
        return (await session.execute(statement)).scalar_one_or_none()

    async def is_allowed(
        self,
        session: AsyncSession,
        *,
        bucket_hmac: bytes,
        now: datetime | None = None,
    ) -> tuple[bool, AuthRateLimit | None]:
        checked_at = now or datetime.now(UTC)
        record = await self.lock_and_get(session, bucket_hmac=bucket_hmac)
        if record is None:
            return True, None
        if record.blocked_until is not None and record.blocked_until > checked_at:
            return False, record
        if record.window_started_at + self._window <= checked_at:
            record.window_started_at = checked_at
            record.attempt_count = 0
            record.blocked_until = None
        return True, record

    def record_failure(
        self,
        session: AsyncSession,
        *,
        record: AuthRateLimit | None,
        bucket_hmac: bytes,
        now: datetime | None = None,
    ) -> None:
        failed_at = now or datetime.now(UTC)
        if record is None:
            record = AuthRateLimit(
                purpose=self._purpose,
                bucket_hmac=bucket_hmac,
                window_started_at=failed_at,
                attempt_count=0,
            )
            session.add(record)
        record.attempt_count += 1
        if record.attempt_count >= self._max_attempts:
            record.blocked_until = failed_at + self._block_for

    async def reset(self, session: AsyncSession, *, record: AuthRateLimit | None) -> None:
        if record is not None:
            await session.delete(record)
