"""Database-backed, privacy-minimized authentication rate limiting."""
from datetime import UTC, datetime, timedelta
import hashlib
import hmac

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import AuthRateLimit


RateLimitState = list[tuple[str, bytes, AuthRateLimit | None]]


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
        self._client_max_attempts = max_attempts * 4
        self._global_max_attempts = max_attempts * 20
        self._window = window
        self._block_for = block_for
        self._purpose = purpose

    def bucket_hmac(self, *, identifier: str, client_signal: str) -> bytes:
        # Malformed credentials still need a stable limiter bucket. Surrogate
        # encoding is confined to this opaque HMAC and never reaches storage.
        material = f"{self._purpose}\0{identifier}\0{client_signal}".encode(
            "utf-8", errors="surrogatepass"
        )
        return hmac.digest(self._hmac_secret.encode("utf-8"), material, hashlib.sha256)

    def _scoped_bucket_hmac(self, *, scope: str, value: str) -> bytes:
        return self.bucket_hmac(identifier=f"{scope}:{value}", client_signal="")

    async def prune_stale(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> None:
        """Bound persistent limiter state without weakening an active block."""
        checked_at = now or datetime.now(UTC)
        stale_before = checked_at - max(self._window, self._block_for)
        await session.execute(
            delete(AuthRateLimit).where(
                AuthRateLimit.purpose == self._purpose,
                AuthRateLimit.window_started_at < stale_before,
                (AuthRateLimit.blocked_until.is_(None) | (AuthRateLimit.blocked_until <= checked_at)),
            )
        )

    async def check_scoped(
        self,
        session: AsyncSession,
        *,
        credential: str,
        client_signal: str,
        now: datetime | None = None,
    ) -> tuple[bool, RateLimitState]:
        """Enforce independent client and credential limits before expensive work."""
        checked_at = now or datetime.now(UTC)
        state: RateLimitState = []
        for scope, value in (
            ("global", "installation"),
            ("client", client_signal),
            ("credential", credential),
        ):
            bucket_hmac = self._scoped_bucket_hmac(scope=scope, value=value)
            allowed, record = await self.is_allowed(
                session,
                bucket_hmac=bucket_hmac,
                now=checked_at,
            )
            state.append((scope, bucket_hmac, record))
            if not allowed:
                return False, state
            if scope == "global":
                # Every scoped request holds the same global advisory lock until
                # commit, so cleanup cannot race another bucket update/reset.
                # Flush a window reset first so the set-based DELETE cannot see
                # and remove this transaction's just-refreshed global row.
                await session.flush()
                await self.prune_stale(session, now=checked_at)
        return True, state

    def record_scoped_failure(
        self,
        session: AsyncSession,
        *,
        state: RateLimitState,
        now: datetime | None = None,
    ) -> None:
        for scope, bucket_hmac, record in state:
            self.record_failure(
                session,
                record=record,
                bucket_hmac=bucket_hmac,
                now=now,
                max_attempts=(
                    self._global_max_attempts
                    if scope == "global"
                    else self._client_max_attempts
                    if scope == "client"
                    else self._max_attempts
                ),
            )

    async def reset_scoped(self, session: AsyncSession, *, state: RateLimitState) -> None:
        for scope, _bucket_hmac, record in state:
            if scope == "global":
                continue
            await self.reset(session, record=record)

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
        max_attempts: int | None = None,
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
        if record.attempt_count >= (max_attempts or self._max_attempts):
            record.blocked_until = failed_at + self._block_for

    async def reset(self, session: AsyncSession, *, record: AuthRateLimit | None) -> None:
        if record is not None:
            await session.delete(record)
