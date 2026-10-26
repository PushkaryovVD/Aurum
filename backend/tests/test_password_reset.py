from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.main import create_app
from app.models.auth import SecurityAuditEvent, UserSession
from app.models.workspace import User
from app.services.password_reset_service import issue_reset_token
# Pytest discovers imported decorated fixtures in this module's namespace.
from tests.test_auth_api import HMAC_SECRET, PASSWORD, _bootstrap_user, auth_settings

ORIGIN = {"Origin": "https://test"}
NEW_PASSWORD = "a brand new test-only passphrase"
GENERIC_REPLY = {"detail": "If the account exists and has an e-mail login, a reset link has been sent"}


@pytest.fixture
def mailbox(monkeypatch) -> list:
    # Fake transport: the tests never talk to a real mail server.
    sent: list = []
    monkeypatch.setattr("app.services.email_service._send_blocking", lambda settings, message: sent.append(message))
    return sent


def _client(settings, test_sessionmaker) -> AsyncClient:
    application = create_app(settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    return AsyncClient(transport=ASGITransport(app=application), base_url="https://test/api")


def _mail_settings(auth_settings):
    return auth_settings.model_copy(
        update={"smtp_host": "smtp.test.invalid", "smtp_username": "sender@example.com", "auth_login_max_attempts": 5}
    )


def _token_from(message) -> str:
    body = message.get_body(preferencelist=("plain",)).get_content()
    match = re.search(r"https://test/reset-password#token=(\S+)", body)
    assert match, body
    return match.group(1)


async def _login(client: AsyncClient, password: str):
    return await client.post("/auth/session", json={"identifier": "owner@example.com", "password": password}, headers=ORIGIN)


async def test_reset_is_unavailable_without_mail(test_sessionmaker, auth_settings):
    async with _client(auth_settings, test_sessionmaker) as client:
        status = await client.get("/auth/status")
        response = await client.post("/auth/password-reset/request", json={"identifier": "owner@example.com"}, headers=ORIGIN)
    assert status.json()["password_reset_available"] is False
    assert response.status_code == 503


async def test_full_reset_changes_password_signs_out_and_burns_the_link(test_sessionmaker, auth_settings, mailbox):
    user_id, _, _ = await _bootstrap_user(test_sessionmaker)
    async with _client(_mail_settings(auth_settings), test_sessionmaker) as client:
        assert (await client.get("/auth/status")).json()["password_reset_available"] is True
        assert (await _login(client, PASSWORD)).status_code == 200

        requested = await client.post("/auth/password-reset/request", json={"identifier": " Owner@Example.com "}, headers=ORIGIN)
        assert requested.status_code == 202
        assert requested.json() == GENERIC_REPLY
        assert len(mailbox) == 1 and mailbox[0]["To"] == "owner@example.com"
        token = _token_from(mailbox[0])

        confirmed = await client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}, headers=ORIGIN)
        assert confirmed.status_code == 204
        reused = await client.post("/auth/password-reset/confirm", json={"token": token, "password": "yet another test-only pass"}, headers=ORIGIN)
        assert reused.status_code == 400

        assert (await _login(client, PASSWORD)).status_code == 401
        assert (await _login(client, NEW_PASSWORD)).status_code == 200

    async with test_sessionmaker() as session:
        sessions = (await session.execute(select(UserSession).where(UserSession.user_id == user_id))).scalars().all()
        # The session opened before the reset is revoked; only the new login is live.
        assert sum(1 for record in sessions if record.revoked_at is None) == 1
        events = (await session.execute(select(SecurityAuditEvent.event_type, SecurityAuditEvent.outcome))).all()
        assert ("password_reset", "success") in events


async def test_unknown_or_non_email_login_gets_the_same_reply_and_no_mail(test_sessionmaker, auth_settings, mailbox):
    await _bootstrap_user(test_sessionmaker, identifier="plain-login")
    async with _client(_mail_settings(auth_settings), test_sessionmaker) as client:
        unknown = await client.post("/auth/password-reset/request", json={"identifier": "nobody@example.com"}, headers=ORIGIN)
        not_mailbox = await client.post("/auth/password-reset/request", json={"identifier": "plain-login"}, headers=ORIGIN)
    assert unknown.status_code == not_mailbox.status_code == 202
    assert unknown.json() == not_mailbox.json() == GENERIC_REPLY
    assert mailbox == []


async def test_disabled_account_gets_no_mail(test_sessionmaker, auth_settings, mailbox):
    await _bootstrap_user(test_sessionmaker, status="disabled")
    async with _client(_mail_settings(auth_settings), test_sessionmaker) as client:
        response = await client.post("/auth/password-reset/request", json={"identifier": "owner@example.com"}, headers=ORIGIN)
    assert response.json() == GENERIC_REPLY
    assert mailbox == []


async def test_tampered_and_expired_links_are_rejected(test_sessionmaker, auth_settings):
    user_id, _, _ = await _bootstrap_user(test_sessionmaker)
    async with test_sessionmaker() as session:
        user = await session.get(User, user_id)
        valid, _ = issue_reset_token(HMAC_SECRET, user, ttl=timedelta(minutes=30))
        expired, _ = issue_reset_token(HMAC_SECRET, user, ttl=timedelta(minutes=30), now=datetime.now(UTC) - timedelta(hours=1))
        forged, _ = issue_reset_token("another-secret-with-at-least-32-bytes!!", user, ttl=timedelta(minutes=30))
    payload, signature = valid.split(".")
    tampered = f"{payload}.{signature[:-2]}AA"
    async with _client(_mail_settings(auth_settings), test_sessionmaker) as client:
        for token in (tampered, expired, forged, "", "not-a-token"):
            response = await client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}, headers=ORIGIN)
            assert response.status_code == 400, token
        # A weak password on a valid link is refused without burning the link.
        weak = await client.post("/auth/password-reset/confirm", json={"token": valid, "password": "short"}, headers=ORIGIN)
        assert weak.status_code == 422
        ok = await client.post("/auth/password-reset/confirm", json={"token": valid, "password": NEW_PASSWORD}, headers=ORIGIN)
        assert ok.status_code == 204


async def test_cross_origin_requests_are_refused(test_sessionmaker, auth_settings, mailbox):
    await _bootstrap_user(test_sessionmaker)
    async with _client(_mail_settings(auth_settings), test_sessionmaker) as client:
        request = await client.post(
            "/auth/password-reset/request",
            json={"identifier": "owner@example.com"},
            headers={"Origin": "https://evil.example"},
        )
        confirm = await client.post(
            "/auth/password-reset/confirm",
            json={"token": "x.y", "password": NEW_PASSWORD},
            headers={"Origin": "https://evil.example"},
        )
    assert request.status_code == confirm.status_code == 404
    assert mailbox == []


async def test_requests_are_rate_limited(test_sessionmaker, auth_settings, mailbox):
    await _bootstrap_user(test_sessionmaker)
    settings = _mail_settings(auth_settings).model_copy(update={"auth_login_max_attempts": 2})
    async with _client(settings, test_sessionmaker) as client:
        codes = [
            (await client.post("/auth/password-reset/request", json={"identifier": "owner@example.com"}, headers=ORIGIN)).status_code
            for _ in range(4)
        ]
    assert codes[:2] == [202, 202]
    assert 429 in codes[2:]
    assert len(mailbox) == 2
