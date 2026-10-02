"""Password, capability-HMAC, CSRF, and same-origin primitives."""
import hashlib
import hmac
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from fastapi import HTTPException, Request

from app.models.auth import UserSession

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def capability_hmac(secret: str, value: str) -> bytes:
    if not secret:
        raise ValueError("HMAC secret must not be empty")
    return hmac.digest(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)


class PasswordService:
    """A small, explicit Argon2id adapter with no alternate hash scheme."""

    def __init__(
        self,
        *,
        memory_cost: int,
        time_cost: int,
        parallelism: int,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._hasher = PasswordHasher(
            memory_cost=memory_cost,
            time_cost=time_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=Type.ID,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(encoded_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except InvalidHashError:
            return True

    capability_hmac = staticmethod(capability_hmac)


def csrf_token_matches(stored_hmac: bytes, supplied_token: str, hmac_secret: str) -> bool:
    candidate = capability_hmac(hmac_secret, supplied_token)
    return hmac.compare_digest(bytes(stored_hmac), candidate)


def _canonical_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, parsed.hostname.casefold(), port
    except ValueError:
        return None


def validate_same_origin(*, origin: str | None, referer: str | None, expected_origin: str) -> bool:
    source = origin if origin is not None else referer
    if source is None:
        return False
    return _canonical_origin(source) == _canonical_origin(expected_origin)


def enforce_csrf(
    request: Request,
    auth_session: UserSession,
    *,
    csrf_token: str | None,
    hmac_secret: str,
    expected_origin: str,
) -> None:
    """Reject unsafe cookie-authenticated requests without both browser checks."""
    if request.method.upper() in SAFE_METHODS:
        return
    if not validate_same_origin(
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        expected_origin=expected_origin,
    ):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")
    if not csrf_token or not csrf_token_matches(auth_session.csrf_secret, csrf_token, hmac_secret):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
