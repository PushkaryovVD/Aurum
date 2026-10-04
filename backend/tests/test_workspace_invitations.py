"""Focused PostgreSQL/API tests for household membership invitations."""
import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import Settings
from app.main import create_app
from app.models.workspace import WorkspaceInvitation, WorkspaceMembership, WorkspaceRole
from app.security.auth import capability_hmac
from tests.test_auth_api import HMAC_SECRET, PASSWORD, _bootstrap_user


GENERIC_INVITATION_ERROR = {"detail": "Invitation is not available"}
ORIGIN_HEADERS = {"Origin": "https://test"}


@pytest.fixture
def invitation_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        app_auth_required=True,
        auth_hmac_secret=HMAC_SECRET,
        auth_argon2_memory_kib=8192,
        auth_argon2_time_cost=1,
        auth_argon2_parallelism=1,
        auth_invitation_max_attempts=3,
        auth_invitation_window_seconds=900,
        auth_invitation_block_seconds=900,
    )


@pytest_asyncio.fixture
async def invitation_client(test_sessionmaker, invitation_settings) -> AsyncGenerator[AsyncClient, None]:
    application = create_app(invitation_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="https://test/api",
    ) as client:
        yield client


async def _login(client: AsyncClient, identifier: str) -> tuple[str, str]:
    response = await client.post(
        "/auth/session",
        json={"identifier": identifier, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return response.json()["csrf_token"], cookie["aurum_session"].value


async def _create_household(client: AsyncClient, csrf_token: str, name: str = "Family") -> UUID:
    response = await client.post(
        "/workspaces",
        json={"display_name": name},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "household"
    assert response.json()["role"] == "owner"
    return UUID(response.json()["id"])


async def _create_invitation(
    client: AsyncClient,
    csrf_token: str,
    workspace_id: UUID,
    recipient: str,
    role: str = "editor",
) -> dict:
    response = await client.post(
        f"/workspaces/{workspace_id}/invitations",
        json={"recipient": recipient, "role": role, "expires_in_seconds": 3600},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_owner_household_and_invitation_persist_only_recipient_and_token_hmac(
    invitation_client,
    test_sessionmaker,
):
    owner_id, personal_workspace_id, _ = await _bootstrap_user(test_sessionmaker)
    csrf_token, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, csrf_token)

    personal_attempt = await invitation_client.post(
        f"/workspaces/{personal_workspace_id}/invitations",
        json={"recipient": "member@example.com", "role": "viewer", "expires_in_seconds": 3600},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": csrf_token},
    )
    assert personal_attempt.status_code == 409

    invitation = await _create_invitation(
        invitation_client,
        csrf_token,
        household_id,
        "  Member@Example.COM  ",
        "viewer",
    )
    assert invitation["token"]
    assert invitation["recipient"] == "member@example.com"
    assert invitation["role"] == "viewer"

    async with test_sessionmaker() as session:
        record = (await session.execute(select(WorkspaceInvitation))).scalar_one()
        assert record.workspace_id == household_id
        assert record.created_by_user_id == owner_id
        assert record.recipient_normalized == "member@example.com"
        assert record.token_hmac == capability_hmac(HMAC_SECRET, invitation["token"])
        assert invitation["token"].encode() not in bytes(record.token_hmac)
        assert record.max_uses == 1
        assert record.uses == 0


async def test_membership_admin_is_owner_only_and_personal_or_owner_membership_is_immutable(
    invitation_client,
    test_sessionmaker,
):
    owner_id, personal_workspace_id, _ = await _bootstrap_user(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker, identifier="editor@example.com", display_name="Editor")
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, owner_csrf)
    invitation = await _create_invitation(
        invitation_client,
        owner_csrf,
        household_id,
        "editor@example.com",
    )

    invitation_client.cookies.clear()
    editor_csrf, _ = await _login(invitation_client, "editor@example.com")
    accepted = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": invitation["token"]},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": editor_csrf},
    )
    assert accepted.status_code == 200

    forbidden = await invitation_client.post(
        f"/workspaces/{household_id}/invitations",
        json={"recipient": "third@example.com", "role": "viewer", "expires_in_seconds": 3600},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": accepted.json()["csrf_token"]},
    )
    assert forbidden.status_code == 403

    invitation_client.cookies.clear()
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    members = await invitation_client.get(f"/workspaces/{household_id}/members")
    assert members.status_code == 200
    owner_membership = next(item for item in members.json() if item["user_id"] == str(owner_id))
    editor_membership = next(item for item in members.json() if item["role"] == "editor")

    owner_change = await invitation_client.patch(
        f"/workspaces/{household_id}/members/{owner_membership['id']}",
        json={"role": "viewer"},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": owner_csrf},
    )
    assert owner_change.status_code == 409

    changed = await invitation_client.patch(
        f"/workspaces/{household_id}/members/{editor_membership['id']}",
        json={"role": "viewer"},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": owner_csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "viewer"

    personal_members = await invitation_client.get(f"/workspaces/{personal_workspace_id}/members")
    assert personal_members.status_code == 409


async def test_existing_account_acceptance_is_recipient_bound_generic_and_one_use(
    invitation_client,
    test_sessionmaker,
):
    await _bootstrap_user(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker, identifier="member@example.com", display_name="Member")
    await _bootstrap_user(test_sessionmaker, identifier="other@example.com", display_name="Other")
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, owner_csrf)
    invitation = await _create_invitation(
        invitation_client,
        owner_csrf,
        household_id,
        "member@example.com",
    )

    invitation_client.cookies.clear()
    other_csrf, _ = await _login(invitation_client, "other@example.com")
    mismatch = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": invitation["token"]},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": other_csrf},
    )
    unknown = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": "unknown-token"},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": other_csrf},
    )
    assert mismatch.status_code == unknown.status_code == 404
    assert mismatch.json() == unknown.json() == GENERIC_INVITATION_ERROR

    invitation_client.cookies.clear()
    member_csrf, _ = await _login(invitation_client, "member@example.com")
    accepted = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": invitation["token"]},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": member_csrf},
    )
    assert accepted.status_code == 200
    assert any(item["id"] == str(household_id) for item in accepted.json()["workspaces"])
    assert accepted.json()["csrf_token"] != member_csrf

    replay = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": invitation["token"]},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": accepted.json()["csrf_token"]},
    )
    assert replay.status_code == 404
    assert replay.json() == GENERIC_INVITATION_ERROR

    async with test_sessionmaker() as session:
        record = (await session.execute(select(WorkspaceInvitation))).scalar_one()
        assert record.uses == 1
        assert record.accepted_by_user_id is not None


async def test_existing_acceptance_requires_csrf_and_malformed_token_is_generic(
    invitation_client,
    test_sessionmaker,
):
    await _bootstrap_user(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker, identifier="member@example.com", display_name="Member")
    invitation_client.cookies.clear()
    csrf_token, _ = await _login(invitation_client, "member@example.com")

    missing_csrf = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": "unknown-token"},
    )
    malformed = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": ""},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": csrf_token},
    )
    assert missing_csrf.status_code == 403
    assert malformed.status_code == 404
    assert malformed.json() == GENERIC_INVITATION_ERROR


async def test_distinct_existing_account_invitations_race_to_one_membership(
    invitation_client,
    test_sessionmaker,
):
    await _bootstrap_user(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker, identifier="member@example.com", display_name="Member")
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, owner_csrf)
    invitations = [
        await _create_invitation(
            invitation_client,
            owner_csrf,
            household_id,
            "member@example.com",
        )
        for _ in range(2)
    ]

    invitation_client.cookies.clear()
    member_csrf, _ = await _login(invitation_client, "member@example.com")
    responses = await asyncio.gather(
        *(
            invitation_client.post(
                "/workspaces/invitations/accept",
                json={"token": invitation["token"]},
                headers={**ORIGIN_HEADERS, "X-CSRF-Token": member_csrf},
            )
            for invitation in invitations
        )
    )
    assert sorted(response.status_code for response in responses) == [200, 404]
    assert next(response for response in responses if response.status_code == 404).json() == (
        GENERIC_INVITATION_ERROR
    )

    async with test_sessionmaker() as session:
        memberships = (
            await session.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == household_id,
                    WorkspaceMembership.user_id.is_not(None),
                    WorkspaceMembership.role == WorkspaceRole.EDITOR,
                    WorkspaceMembership.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        records = (await session.execute(select(WorkspaceInvitation))).scalars().all()
        assert len(memberships) == 1
        assert sorted(record.uses for record in records) == [0, 1]


async def test_public_acceptance_atomically_bootstraps_new_account_and_only_one_racer_wins(
    invitation_client,
    test_sessionmaker,
):
    await _bootstrap_user(test_sessionmaker)
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, owner_csrf)
    invitation = await _create_invitation(
        invitation_client,
        owner_csrf,
        household_id,
        "new@example.com",
        "viewer",
    )
    invitation_client.cookies.clear()
    payload = {
        "token": invitation["token"],
        "identifier": " NEW@example.com ",
        "display_name": "New Member",
        "password": PASSWORD,
    }

    first, second = await asyncio.gather(
        invitation_client.post("/auth/invitations/accept", json=payload),
        invitation_client.post("/auth/invitations/accept", json=payload),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 404]
    failed = first if first.status_code == 404 else second
    succeeded = second if first.status_code == 404 else first
    assert failed.json() == GENERIC_INVITATION_ERROR
    assert succeeded.json()["user"]["identifier"] == "new@example.com"
    assert len(succeeded.json()["workspaces"]) == 2

    async with test_sessionmaker() as session:
        memberships = (
            await session.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == household_id,
                    WorkspaceMembership.role == WorkspaceRole.VIEWER,
                    WorkspaceMembership.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(memberships) == 1
        record = (await session.execute(select(WorkspaceInvitation))).scalar_one()
        assert record.uses == 1
        assert record.accepted_at is not None


@pytest.mark.parametrize("state", ["expired", "revoked", "used"])
async def test_unavailable_invitation_states_are_generic(
    invitation_client,
    test_sessionmaker,
    state: str,
):
    await _bootstrap_user(test_sessionmaker)
    await _bootstrap_user(test_sessionmaker, identifier="member@example.com", display_name="Member")
    owner_csrf, _ = await _login(invitation_client, "owner@example.com")
    household_id = await _create_household(invitation_client, owner_csrf)
    invitation = await _create_invitation(
        invitation_client,
        owner_csrf,
        household_id,
        "member@example.com",
    )
    async with test_sessionmaker() as session:
        record = (await session.execute(select(WorkspaceInvitation))).scalar_one()
        if state == "expired":
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif state == "revoked":
            record.revoked_at = datetime.now(UTC)
        else:
            record.uses = 1
        await session.commit()

    invitation_client.cookies.clear()
    csrf_token, _ = await _login(invitation_client, "member@example.com")
    response = await invitation_client.post(
        "/workspaces/invitations/accept",
        json={"token": invitation["token"]},
        headers={**ORIGIN_HEADERS, "X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 404
    assert response.json() == GENERIC_INVITATION_ERROR
