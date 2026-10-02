"""Unit tests for authentication configuration and security primitives."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.security.auth import PasswordService, csrf_token_matches, enforce_csrf, validate_same_origin


TEST_HMAC_SECRET = "test-only-hmac-secret-with-at-least-32-bytes"


def test_passwords_use_argon2id_and_support_rehash_detection():
    service = PasswordService(memory_cost=8192, time_cost=1, parallelism=1)
    encoded = service.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded
    assert service.verify(encoded, "correct horse battery staple") is True
    assert service.verify(encoded, "wrong") is False
    assert service.needs_rehash(encoded) is False

    stronger = PasswordService(memory_cost=16384, time_cost=2, parallelism=1)
    assert stronger.needs_rehash(encoded) is True


def test_invalid_password_hash_is_rejected_without_leaking_library_errors():
    service = PasswordService(memory_cost=8192, time_cost=1, parallelism=1)
    assert service.verify("not-an-argon2-hash", "password") is False


def test_authentication_remains_disabled_by_default():
    settings = Settings(_env_file=None)
    assert settings.app_auth_required is False
    assert settings.auth_hmac_secret.get_secret_value() == ""
    assert settings.docs_enabled is True


def test_application_auth_forces_api_docs_off():
    settings = Settings(
        _env_file=None,
        environment="production",
        app_auth_required=True,
        auth_hmac_secret=TEST_HMAC_SECRET,
        enable_docs=True,
    )
    assert settings.docs_enabled is False


@pytest.mark.parametrize("secret", ["", "short", "change-me", "replace-me-with-a-secret"])
def test_non_development_auth_requires_a_strong_non_default_secret(secret: str):
    with pytest.raises(ValidationError, match="HMAC secret"):
        Settings(
            _env_file=None,
            environment="production",
            app_auth_required=True,
            auth_hmac_secret=secret,
        )


def test_session_lifetimes_and_argon2_parameters_fail_closed():
    with pytest.raises(ValidationError, match="idle lifetime"):
        Settings(
            _env_file=None,
            app_auth_required=True,
            auth_hmac_secret=TEST_HMAC_SECRET,
            auth_session_idle_seconds=7200,
            auth_session_absolute_seconds=3600,
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_argon2_memory_kib=1024)


def test_csrf_comparison_is_session_bound_and_constant_time_compatible():
    csrf_token = "csrf-token-for-this-session"
    stored = PasswordService.capability_hmac(TEST_HMAC_SECRET, csrf_token)

    assert csrf_token_matches(stored, csrf_token, TEST_HMAC_SECRET) is True
    assert csrf_token_matches(stored, "other-token", TEST_HMAC_SECRET) is False


@pytest.mark.parametrize(
    ("origin", "referer", "expected"),
    [
        ("https://aurum.example", None, True),
        (None, "https://aurum.example/settings", True),
        ("https://evil.example", "https://aurum.example/settings", False),
        (None, None, False),
        ("https://aurum.example.evil", None, False),
    ],
)
def test_same_origin_uses_origin_then_referer(origin, referer, expected):
    assert validate_same_origin(
        origin=origin,
        referer=referer,
        expected_origin="https://aurum.example",
    ) is expected


def test_configured_lifetimes_are_exposed_as_timedeltas():
    settings = Settings(
        _env_file=None,
        app_auth_required=True,
        auth_hmac_secret=TEST_HMAC_SECRET,
        auth_session_idle_seconds=900,
        auth_session_absolute_seconds=3600,
    )
    assert settings.auth_session_idle_lifetime == timedelta(seconds=900)
    assert settings.auth_session_absolute_lifetime == timedelta(seconds=3600)


def test_csrf_dependency_rejects_missing_token_and_cross_origin():
    stored = PasswordService.capability_hmac(TEST_HMAC_SECRET, "valid-token")
    session = type("Session", (), {"csrf_secret": stored})()

    def request(origin: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "https",
                "server": ("aurum.example", 443),
                "path": "/api/test",
                "headers": [(b"origin", origin.encode())],
            }
        )

    with pytest.raises(HTTPException, match="CSRF"):
        enforce_csrf(
            request("https://aurum.example"),
            session,
            csrf_token=None,
            hmac_secret=TEST_HMAC_SECRET,
            expected_origin="https://aurum.example",
        )
    with pytest.raises(HTTPException, match="origin"):
        enforce_csrf(
            request("https://evil.example"),
            session,
            csrf_token="valid-token",
            hmac_secret=TEST_HMAC_SECRET,
            expected_origin="https://aurum.example",
        )
    enforce_csrf(
        request("https://aurum.example"),
        session,
        csrf_token="valid-token",
        hmac_secret=TEST_HMAC_SECRET,
        expected_origin="https://aurum.example",
    )
