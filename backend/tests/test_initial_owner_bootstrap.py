"""PostgreSQL/API contract for the one-time first personal owner ceremony."""
import asyncio
from datetime import timedelta
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.api.deps import get_session
from app.main import create_app
from app.models.auth import InitialOwnerBootstrap, SecurityAuditEvent, UserSession
from app.models.workspace import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.services.workspace_service import issue_initial_owner_bootstrap_code
# Pytest discovers imported decorated fixtures in this module's namespace.
from tests.test_auth_api import HMAC_SECRET, _bootstrap_user, auth_client, auth_settings

ORIGIN_HEADERS = {"Origin": "https://test"}
PAYLOAD = {
    "identifier": "  OWNER@EXAMPLE.COM ",
    "display_name": "Private owner",
    "password": "correct horse battery staple",
}


async def _issue_code(test_sessionmaker) -> str:
    async with test_sessionmaker() as session:
        code = await issue_initial_owner_bootstrap_code(
            session, hmac_secret=HMAC_SECRET, expires_in=timedelta(minutes=15)
        )
        await session.commit()
    assert code is not None
    return code


async def _bootstrap(client, code: str):
    return await client.post(
        "/auth/bootstrap/initial-owner",
        json={**PAYLOAD, "bootstrap_code": code},
        headers=ORIGIN_HEADERS,
    )


async def test_initial_owner_bootstrap_is_atomic_audited_and_preserves_legacy_namespace(
    auth_client, test_sessionmaker
):
    # The seeded default account is representative legacy NULL-namespace data.
    async with test_sessionmaker() as session:
        legacy_account_workspace = (
            await session.execute(text("SELECT workspace_id FROM accounts LIMIT 1"))
        ).scalar_one()
    assert legacy_account_workspace is None

    code = await _issue_code(test_sessionmaker)
    response = await _bootstrap(auth_client, code)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["identifier"] == "owner@example.com"
    assert body["csrf_token"]
    assert "set-cookie" in response.headers
    authenticated = await auth_client.get("/auth/me")
    assert authenticated.status_code == 200
    assert authenticated.json() == body

    async with test_sessionmaker() as session:
        user = (await session.execute(select(User))).scalar_one()
        workspace = (await session.execute(select(Workspace))).scalar_one()
        membership = (await session.execute(select(WorkspaceMembership))).scalar_one()
        audit = (await session.execute(select(SecurityAuditEvent))).scalar_one()
        assert user.normalized_login == "owner@example.com"
        assert user.personal_workspace_id == workspace.id
        assert workspace.personal_owner_user_id == user.id
        assert membership.user_id == user.id and membership.workspace_id == workspace.id
        assert membership.role == WorkspaceRole.OWNER
        assert audit.actor_user_id == user.id and audit.workspace_id == workspace.id
        assert audit.event_type == "initial_owner_bootstrap" and audit.outcome == "success"
        assert (await session.get(InitialOwnerBootstrap, 1)) is None
        assert (await session.execute(text("SELECT workspace_id FROM accounts LIMIT 1"))).scalar_one() is None
        assert len((await session.execute(select(UserSession))).scalars().all()) == 1


async def test_initial_owner_same_origin_failure_is_audited_rate_limited_and_non_consuming(
    auth_client,
    test_sessionmaker,
):
    code = await _issue_code(test_sessionmaker)
    rejected = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json={"bootstrap_code": code, **PAYLOAD},
        headers={"Origin": "https://evil.example"},
    )
    assert rejected.status_code == 404
    async with test_sessionmaker() as session:
        assert (await session.get(InitialOwnerBootstrap, 1)) is not None
        audit = (await session.execute(select(SecurityAuditEvent))).scalar_one()
        assert audit.event_type == "initial_owner_bootstrap"
        assert audit.outcome == "failure"

    succeeded = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json={"bootstrap_code": code, **PAYLOAD},
        headers=ORIGIN_HEADERS,
    )
    assert succeeded.status_code == 200


@pytest.mark.parametrize("display_name_length", [81, 100])
async def test_bootstrap_caps_derived_workspace_name_for_valid_owner_display_names(
    auth_client, test_sessionmaker, display_name_length
):
    code = await _issue_code(test_sessionmaker)
    response = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json={
            **PAYLOAD,
            "bootstrap_code": code,
            "display_name": "O" * display_name_length,
        },
        headers=ORIGIN_HEADERS,
    )

    assert response.status_code == 200, response.text
    async with test_sessionmaker() as session:
        user = (await session.execute(select(User))).scalar_one()
        workspace = (await session.execute(select(Workspace))).scalar_one()
    assert len(user.display_name) == display_name_length
    assert workspace.display_name.endswith("'s private workspace")
    assert len(workspace.display_name) <= 100


async def test_normalized_identifier_over_database_limit_is_generic_audited_and_rate_limited(
    auth_client, test_sessionmaker
):
    code = await _issue_code(test_sessionmaker)
    expanding_identifier = "\ufb03" * 107

    failed = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json={
            **PAYLOAD,
            "bootstrap_code": code,
            "identifier": expanding_identifier,
        },
        headers=ORIGIN_HEADERS,
    )

    assert failed.status_code == 404
    assert failed.json() == {"detail": "Initial owner setup is not available"}
    async with test_sessionmaker() as session:
        outcomes = (
            await session.execute(
                select(SecurityAuditEvent.outcome).where(
                    SecurityAuditEvent.event_type == "initial_owner_bootstrap"
                )
            )
        ).scalars().all()
        assert outcomes == ["failure"]
        assert (await session.get(InitialOwnerBootstrap, 1)) is not None

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


@pytest.mark.parametrize(
    "override",
    [
        {"identifier": "owner\x00@example.com"},
        {"display_name": "Private\x00owner"},
        {"bootstrap_code": "valid\x00code"},
        {"password": "valid-password\x00suffix"},
        {"bootstrap_code": "\ud800"},
        {"bootstrap_code": "\udfff"},
        {"identifier": "owner\ud800@example.com"},
        {"identifier": "owner\udfff@example.com"},
        {"display_name": "Private\ud800owner"},
        {"display_name": "Private\udfffowner"},
        {"password": "valid-password\ud800"},
        {"password": "valid-password\udfff"},
    ],
)
async def test_non_utf8_text_is_generic_audited_and_does_not_mutate_or_consume_code(
    auth_client, test_sessionmaker, override
):
    code = await _issue_code(test_sessionmaker)
    failed = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        content=json.dumps(
            {**PAYLOAD, "bootstrap_code": code, **override}, ensure_ascii=True
        ).encode("ascii"),
        headers={**ORIGIN_HEADERS, "Content-Type": "application/json"},
    )

    assert failed.status_code == 404
    assert failed.json() == {"detail": "Initial owner setup is not available"}
    async with test_sessionmaker() as session:
        assert not (await session.execute(select(User))).scalars().all()
        assert not (await session.execute(select(Workspace))).scalars().all()
        assert not (await session.execute(select(UserSession))).scalars().all()
        assert (await session.get(InitialOwnerBootstrap, 1)) is not None
        outcomes = (
            await session.execute(
                select(SecurityAuditEvent.outcome).where(
                    SecurityAuditEvent.event_type == "initial_owner_bootstrap"
                )
            )
        ).scalars().all()
        assert outcomes == ["failure"]

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


@pytest.mark.parametrize("candidate", ["", "wrong-code-" + "x" * 32, "z" * 43])
async def test_wrong_code_is_generic_rate_limited_and_does_not_consume_pending_code(
    auth_client, test_sessionmaker, candidate
):
    code = await _issue_code(test_sessionmaker)
    failed = await _bootstrap(auth_client, candidate)
    assert failed.status_code == 404
    assert failed.json() == {"detail": "Initial owner setup is not available"}

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


async def test_rate_limited_bootstrap_attempt_is_audited(auth_client, test_sessionmaker):
    await _issue_code(test_sessionmaker)

    first = await _bootstrap(auth_client, "wrong-code-1")
    second = await _bootstrap(auth_client, "wrong-code-2")
    blocked = await _bootstrap(auth_client, "wrong-code-3")

    assert first.status_code == second.status_code == 404
    assert blocked.status_code == 429
    async with test_sessionmaker() as session:
        outcomes = (
            await session.execute(
                select(SecurityAuditEvent.outcome)
                .where(SecurityAuditEvent.event_type == "initial_owner_bootstrap")
                .order_by(SecurityAuditEvent.created_at, SecurityAuditEvent.id)
            )
        ).scalars().all()
    assert outcomes == ["failure", "failure", "rate_limited"]


async def test_bootstrap_rejects_spoofed_loopback_host_over_remote_http(
    test_sessionmaker, auth_settings
):
    code = await _issue_code(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session():
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("203.0.113.10", 12345))
    async with AsyncClient(transport=transport, base_url="http://localhost/api") as client:
        response = await _bootstrap(client, code)

    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}


async def test_bootstrap_allows_default_nginx_chain_for_host_loopback_client(
    test_sessionmaker, auth_settings
):
    code = await _issue_code(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session():
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("172.31.254.3", 12345))
    async with AsyncClient(transport=transport, base_url="http://localhost:3000/api") as client:
        response = await client.post(
            "/auth/bootstrap/initial-owner",
            json={**PAYLOAD, "bootstrap_code": code},
            headers={
                "Origin": "http://localhost:3000",
                "X-Forwarded-Proto": "http",
                "X-Real-IP": "172.31.254.1",
            },
        )

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "override",
    [
        {"bootstrap_code": "x" * 1025},
        {"identifier": "x" * 321},
        {"display_name": "x" * 101},
        {"password": "short"},
        {"password": "x" * 1025},
        {"password": ["not-a-password"]},
    ],
)
async def test_invalid_bootstrap_payloads_are_generic_and_do_not_consume_code(
    auth_client, test_sessionmaker, override
):
    code = await _issue_code(test_sessionmaker)
    response = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json={**PAYLOAD, "bootstrap_code": code, **override},
        headers=ORIGIN_HEADERS,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


async def test_non_object_bootstrap_payload_is_generic_and_does_not_consume_code(
    auth_client, test_sessionmaker
):
    code = await _issue_code(test_sessionmaker)
    response = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        json=[code],
        headers=ORIGIN_HEADERS,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


async def test_malformed_json_bootstrap_payload_is_generic_and_does_not_consume_code(
    auth_client, test_sessionmaker
):
    code = await _issue_code(test_sessionmaker)
    response = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        content=b'{"bootstrap_code":',
        headers={**ORIGIN_HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
async def test_non_utf8_encoded_bootstrap_payload_is_generic_and_does_not_consume_code(
    auth_client, test_sessionmaker, encoding
):
    code = await _issue_code(test_sessionmaker)
    body = json.dumps({**PAYLOAD, "bootstrap_code": code}).encode(encoding)
    response = await auth_client.post(
        "/auth/bootstrap/initial-owner",
        content=body,
        headers={**ORIGIN_HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}

    succeeded = await _bootstrap(auth_client, code)
    assert succeeded.status_code == 200, succeeded.text


async def test_expired_code_cannot_create_an_owner(auth_client, test_sessionmaker):
    async with test_sessionmaker() as session:
        expired_code = await issue_initial_owner_bootstrap_code(
            session, hmac_secret=HMAC_SECRET, expires_in=timedelta(seconds=-1)
        )
        await session.commit()
    assert expired_code is not None

    response = await _bootstrap(auth_client, expired_code)
    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}
    async with test_sessionmaker() as session:
        assert not (await session.execute(select(User))).scalars().all()
        assert (await session.get(InitialOwnerBootstrap, 1)) is not None

    status = await auth_client.get("/auth/status")
    assert status.status_code == 200
    assert status.json()["initial_owner_bootstrap_required"] is True
    assert status.json()["initial_owner_bootstrap_available"] is False


async def test_replay_existing_user_and_competing_requests_fail_closed(auth_client, test_sessionmaker):
    code = await _issue_code(test_sessionmaker)
    first, second = await asyncio.gather(_bootstrap(auth_client, code), _bootstrap(auth_client, code))
    assert sorted([first.status_code, second.status_code]) == [200, 404]

    replay = await _bootstrap(auth_client, code)
    assert replay.status_code == 404

    # A code issued before an operator-created legacy owner cannot claim it.
    async with test_sessionmaker() as session:
        stale_code = await issue_initial_owner_bootstrap_code(
            session, hmac_secret=HMAC_SECRET, expires_in=timedelta(minutes=15)
        )
        await session.commit()
    assert stale_code is None


async def test_existing_user_rejects_a_previously_issued_code(auth_client, test_sessionmaker):
    code = await _issue_code(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker)

    response = await _bootstrap(auth_client, code)
    assert response.status_code == 404
    async with test_sessionmaker() as session:
        assert (await session.execute(select(User))).scalars().all()
        assert (await session.get(InitialOwnerBootstrap, 1)) is not None
