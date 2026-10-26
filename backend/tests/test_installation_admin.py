"""Installation administration: permissions, safety rules, blocking and deletion."""
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import telegram_bot
from app.api.deps import get_session
from app.core.config import Settings
from app.main import create_app
from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.auth import SecurityAuditEvent, TelegramIdentity, UserSession
from app.models.enums import AccountType, AssetClass, TransactionType
from app.models.goal import Goal, GoalContribution
from app.models.tag import Tag
from app.models.transaction import Transaction
from app.models.workspace import (
    User,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceStatus,
)
from app.services.workspace_deletion_service import owned_tables
from app.services.workspace_service import create_household
from tests.test_auth_api import HMAC_SECRET, PASSWORD, _bootstrap_user

ORIGIN = {"Origin": "https://test"}
TELEGRAM_USER = 515151


@pytest.fixture
def admin_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        app_auth_required=True,
        auth_hmac_secret=HMAC_SECRET,
        auth_argon2_memory_kib=8192,
        auth_argon2_time_cost=1,
        auth_argon2_parallelism=1,
    )


@pytest_asyncio.fixture
async def app_factory(test_sessionmaker, admin_settings):
    """Each call returns a fresh client with its own cookie jar (one per person)."""
    application = create_app(admin_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    clients: list[AsyncClient] = []

    def make() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=application), base_url="https://test/api")
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


class Person:
    def __init__(self, client: AsyncClient, user_id: UUID, personal_id: UUID) -> None:
        self.client = client
        self.user_id = user_id
        self.personal_id = personal_id
        self.csrf = ""

    def headers(self, workspace_id: UUID | None = None) -> dict[str, str]:
        headers = {**ORIGIN, "X-CSRF-Token": self.csrf}
        if workspace_id is not None:
            headers["X-Aurum-Workspace"] = str(workspace_id)
        return headers

    async def login(self, identifier: str):
        response = await self.client.post(
            "/auth/session", json={"identifier": identifier, "password": PASSWORD}, headers=ORIGIN
        )
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    async def post(self, path: str, json: dict | None = None, workspace_id: UUID | None = None):
        return await self.client.post(path, json=json, headers=self.headers(workspace_id))

    async def get(self, path: str, workspace_id: UUID | None = None):
        return await self.client.get(path, headers=self.headers(workspace_id))


async def _person(test_sessionmaker, make, identifier: str, *, admin: bool = False) -> Person:
    user_id, personal_id, _ = await _bootstrap_user(test_sessionmaker, identifier=identifier, display_name=identifier.split("@")[0])
    if admin:
        async with test_sessionmaker() as session:
            await session.execute(update(User).where(User.id == user_id).values(is_admin=True))
            await session.commit()
    person = Person(make(), user_id, personal_id)
    response = await person.login(identifier)
    assert response.status_code == 200, response.text
    return person


async def test_non_admin_is_refused_on_every_admin_endpoint(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    member = await _person(test_sessionmaker, app_factory, "member@example.com")

    assert (await member.get("/admin/users")).status_code == 403
    assert (await member.get("/admin/workspaces")).status_code == 403
    for action in ("block", "unblock", "grant-admin", "revoke-admin"):
        assert (await member.post(f"/admin/users/{admin.user_id}/{action}")).status_code == 403
    for action in ("block", "unblock"):
        assert (await member.post(f"/admin/workspaces/{admin.personal_id}/{action}")).status_code == 403
    deleted = await member.post(f"/admin/workspaces/{admin.personal_id}/delete", json={"confirm_name": "x"})
    assert deleted.status_code == 403
    async with test_sessionmaker() as session:
        assert (await session.get(User, admin.user_id)).is_admin is True


async def test_session_reports_admin_flag_and_admin_list_hides_finances(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    member = await _person(test_sessionmaker, app_factory, "member@example.com")
    me = (await admin.get("/auth/me")).json()
    assert me["user"]["is_admin"] is True
    assert me["active_workspace"]["status"] == "active"
    assert (await member.get("/auth/me")).json()["user"]["is_admin"] is False

    users = (await admin.get("/admin/users")).json()
    by_login = {row["identifier"]: row for row in users}
    assert by_login["admin@example.com"]["is_self"] is True
    assert by_login["member@example.com"]["last_login_at"] is not None
    assert by_login["member@example.com"]["memberships"] == [
        {
            "workspace_id": str(member.personal_id),
            "display_name": "Private workspace",
            "kind": "personal",
            "role": "owner",
            "status": "active",
        }
    ]
    assert "balance" not in str(users) and "amount" not in str(users)
    workspaces = (await admin.get("/admin/workspaces")).json()
    assert {row["id"] for row in workspaces} == {str(admin.personal_id), str(member.personal_id)}


async def test_admin_cannot_block_or_demote_self_and_one_admin_always_remains(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    other = await _person(test_sessionmaker, app_factory, "other@example.com")

    assert (await admin.post(f"/admin/users/{admin.user_id}/block")).status_code == 409
    assert (await admin.post(f"/admin/users/{admin.user_id}/revoke-admin")).status_code == 409

    granted = await admin.post(f"/admin/users/{other.user_id}/grant-admin")
    assert granted.status_code == 200 and granted.json()["is_admin"] is True
    # The new admin demotes the first one; the remaining admin cannot demote themselves.
    assert (await other.post(f"/admin/users/{admin.user_id}/revoke-admin")).status_code == 200
    assert (await other.post(f"/admin/users/{other.user_id}/revoke-admin")).status_code == 409
    # The demoted admin lost every admin capability immediately.
    assert (await admin.post(f"/admin/users/{other.user_id}/revoke-admin")).status_code == 403

    async with test_sessionmaker() as session:
        admins = (await session.execute(select(User.id).where(User.is_admin.is_(True)))).scalars().all()
        assert admins == [other.user_id]
        events = (
            await session.execute(
                select(SecurityAuditEvent.event_type, SecurityAuditEvent.outcome).where(
                    SecurityAuditEvent.event_type.like("admin_%")
                )
            )
        ).all()
        assert ("admin_user_blocked", "failure") in events
        assert ("admin_role_granted", "success") in events
        assert ("admin_role_revoked", "success") in events


async def test_blocking_a_user_revokes_every_session_and_login(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    member = await _person(test_sessionmaker, app_factory, "member@example.com")
    second_device = Person(app_factory(), member.user_id, member.personal_id)
    assert (await second_device.login("member@example.com")).status_code == 200

    blocked = await admin.post(f"/admin/users/{member.user_id}/block")
    assert blocked.status_code == 200 and blocked.json()["status"] == "disabled"

    assert (await member.get("/auth/me")).status_code == 401
    assert (await second_device.get("/accounts")).status_code == 401
    assert (await member.login("member@example.com")).status_code == 401
    async with test_sessionmaker() as session:
        open_sessions = await session.scalar(
            select(func.count()).select_from(UserSession).where(
                UserSession.user_id == member.user_id, UserSession.revoked_at.is_(None)
            )
        )
        assert open_sessions == 0

    assert (await admin.post(f"/admin/users/{member.user_id}/unblock")).status_code == 200
    assert (await member.login("member@example.com")).status_code == 200


async def test_blocked_workspace_is_closed_to_every_member_but_keeps_data(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    owner = await _person(test_sessionmaker, app_factory, "owner@example.com")
    household = (await owner.post("/workspaces", json={"display_name": "Family"})).json()
    family_id = UUID(household["id"])
    assert (await owner.get("/accounts", workspace_id=family_id)).status_code == 200

    assert (await admin.post(f"/admin/workspaces/{family_id}/block")).json()["status"] == "blocked"

    response = await owner.get("/accounts", workspace_id=family_id)
    assert response.status_code == 423
    assert response.json() == {"detail": "Workspace is blocked"}
    me = (await owner.get("/auth/me", workspace_id=family_id)).json()
    assert me["active_workspace"] == {**me["active_workspace"], "id": str(family_id), "status": "blocked"}
    invite = await owner.post(
        f"/workspaces/{family_id}/invitations",
        json={"recipient": "x@example.com", "role": "viewer", "expires_in_seconds": 3600},
    )
    assert invite.status_code == 423
    # The owner may not delete a space an administrator froze.
    assert (await owner.post(f"/workspaces/{family_id}/delete", json={"confirm_name": "Family"})).status_code == 423
    # The personal space stays usable.
    assert (await owner.get("/accounts", workspace_id=owner.personal_id)).status_code == 200

    async with test_sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Account).where(Account.workspace_id == family_id))

    assert (await admin.post(f"/admin/workspaces/{family_id}/unblock")).json()["status"] == "active"
    assert (await owner.get("/accounts", workspace_id=family_id)).status_code == 200


async def test_blocked_personal_workspace_falls_back_to_an_open_one_on_login(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    owner = await _person(test_sessionmaker, app_factory, "owner@example.com")
    family_id = UUID((await owner.post("/workspaces", json={"display_name": "Family"})).json()["id"])
    await admin.post(f"/admin/workspaces/{owner.personal_id}/block")

    body = (await owner.login("owner@example.com")).json()
    assert body["active_workspace"]["id"] == str(family_id)
    assert {row["id"]: row["status"] for row in body["workspaces"]}[str(owner.personal_id)] == "blocked"


async def _fill_workspace(session: AsyncSession, workspace_id: UUID, label: str) -> None:
    account = Account(workspace_id=workspace_id, name=f"{label} card", type=AccountType.DEBIT_CARD, currency="KZT")
    tag = Tag(workspace_id=workspace_id, name=f"{label} tag")
    session.add_all([account, tag])
    await session.flush()
    transaction = Transaction(
        workspace_id=workspace_id,
        account_id=account.id,
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        transaction_amount=Decimal("10.00"),
        description=f"{label} coffee",
        date=date(2026, 1, 5),
    )
    transaction.tags.append(tag)
    goal = Goal(workspace_id=workspace_id, name=f"{label} goal", target_amount=Decimal("100.00"))
    asset = Asset(workspace_id=workspace_id, name=f"{label} flat", asset_class=AssetClass.REAL_ESTATE)
    session.add_all([transaction, goal, asset])
    await session.flush()
    session.add_all(
        [
            GoalContribution(goal_id=goal.id, amount=Decimal("5.00"), date=date(2026, 1, 6)),
            AssetValuation(asset_id=asset.id, value=Decimal("1000.00"), as_of_date=date(2026, 1, 6)),
        ]
    )


async def _owned_row_counts(session: AsyncSession, workspace_id: UUID) -> dict[str, int]:
    counts = {}
    for table, predicate in owned_tables(workspace_id):
        counts[table.name] = await session.scalar(select(func.count()).select_from(table).where(predicate))
    return counts


async def test_owner_deletes_household_with_all_its_data_and_nothing_else(app_factory, test_sessionmaker):
    owner = await _person(test_sessionmaker, app_factory, "owner@example.com")
    editor = await _person(test_sessionmaker, app_factory, "editor@example.com")
    stranger = await _person(test_sessionmaker, app_factory, "stranger@example.com")
    async with test_sessionmaker() as session:
        family, _ = await create_household(session, creator_id=owner.user_id, display_name="Family")
        other, _ = await create_household(session, creator_id=stranger.user_id, display_name="Family")
        session.add(WorkspaceMembership(workspace_id=family.id, user_id=editor.user_id, role=WorkspaceRole.EDITOR))
        await _fill_workspace(session, family.id, "family")
        await _fill_workspace(session, other.id, "other")
        await _fill_workspace(session, owner.personal_id, "personal")
        session.add(TelegramIdentity(user_id=editor.user_id, default_workspace_id=family.id, telegram_user_id=TELEGRAM_USER))
        session.add(SecurityAuditEvent(actor_user_id=owner.user_id, workspace_id=family.id, event_type="probe", outcome="success"))
        await session.commit()
        family_id, other_id = family.id, other.id
    invite = await owner.post(
        f"/workspaces/{family_id}/invitations",
        json={"recipient": "new@example.com", "role": "viewer", "expires_in_seconds": 3600},
    )
    assert invite.status_code == 201

    async with test_sessionmaker() as session:
        before_other = await _owned_row_counts(session, other_id)
        before_personal = await _owned_row_counts(session, owner.personal_id)
        before_family = await _owned_row_counts(session, family_id)
    assert before_family["transactions"] == 1 and before_family["goal_contributions"] == 1
    assert before_family["asset_valuations"] == 1 and before_family["transaction_tags"] == 1

    # Only the owner, only with the exact name.
    assert (await editor.post(f"/workspaces/{family_id}/delete", json={"confirm_name": "Family"})).status_code == 403
    wrong = await owner.post(f"/workspaces/{family_id}/delete", json={"confirm_name": "Famly"})
    assert wrong.status_code == 409
    personal = await owner.post(f"/workspaces/{owner.personal_id}/delete", json={"confirm_name": "Private workspace"})
    assert personal.status_code == 409
    async with test_sessionmaker() as session:
        assert await _owned_row_counts(session, family_id) == before_family

    deleted = await owner.post(f"/workspaces/{family_id}/delete", json={"confirm_name": " Family "})
    assert deleted.status_code == 204, deleted.text

    async with test_sessionmaker() as session:
        assert await session.get(Workspace, family_id) is None
        assert set((await _owned_row_counts(session, family_id)).values()) == {0}
        assert await _owned_row_counts(session, other_id) == before_other
        assert await _owned_row_counts(session, owner.personal_id) == before_personal
        assert not (await session.execute(select(WorkspaceInvitation))).scalars().all()
        identity = (await session.execute(select(TelegramIdentity))).scalar_one()
        assert identity.default_workspace_id == editor.personal_id
        assert identity.default_account_id is None
        probe = (await session.execute(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "probe"))).scalar_one()
        assert probe.workspace_id is None
        record = (
            await session.execute(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.event_type == "workspace_deleted", SecurityAuditEvent.outcome == "success"
                )
            )
        ).scalar_one()
        assert record.target_id == str(family_id) and record.actor_user_id == owner.user_id
    # Members whose client still points at the deleted space get a clean 404.
    assert (await editor.get("/accounts", workspace_id=family_id)).status_code == 404


async def test_admin_can_delete_any_household_but_never_a_personal_space(app_factory, test_sessionmaker):
    admin = await _person(test_sessionmaker, app_factory, "admin@example.com", admin=True)
    owner = await _person(test_sessionmaker, app_factory, "owner@example.com")
    family_id = UUID((await owner.post("/workspaces", json={"display_name": "Family"})).json()["id"])
    await admin.post(f"/admin/workspaces/{family_id}/block")

    refused = await admin.post(f"/admin/workspaces/{owner.personal_id}/delete", json={"confirm_name": "Private workspace"})
    assert refused.status_code == 409
    assert (await admin.post(f"/admin/workspaces/{family_id}/delete", json={"confirm_name": "Family"})).status_code == 204
    async with test_sessionmaker() as session:
        assert await session.get(Workspace, family_id) is None
        assert await session.get(Workspace, owner.personal_id) is not None
        assert await session.scalar(
            select(func.count()).select_from(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "admin_workspace_deleted")
        ) == 2
    me = (await owner.get("/auth/me")).json()
    assert [row["id"] for row in me["workspaces"]] == [str(owner.personal_id)]


@pytest.fixture
def bot(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(telegram_bot, "AsyncSessionLocal", test_sessionmaker)
    instance = object.__new__(telegram_bot.TelegramBot)
    instance.webapp_url = ""
    return instance


async def test_bot_refuses_blocked_users_and_blocked_spaces(bot, test_sessionmaker):
    user_id, personal_id, _ = await _bootstrap_user(test_sessionmaker)
    async with test_sessionmaker() as session:
        family, _ = await create_household(session, creator_id=user_id, display_name="Family")
        session.add(TelegramIdentity(user_id=user_id, default_workspace_id=family.id, telegram_user_id=TELEGRAM_USER))
        family.status = WorkspaceStatus.BLOCKED
        await session.commit()
        family_id = family.id

    assert await bot.select_space(TELEGRAM_USER, family_id.hex) == "Пространство недоступно"
    assert "заблокировано администратором" in await bot.help_text(TELEGRAM_USER)
    assert (await bot.select_space(TELEGRAM_USER, personal_id.hex)).startswith("Пространство: Private workspace")

    async with test_sessionmaker() as session:
        await session.execute(text("UPDATE users SET status = 'disabled' WHERE id = :id"), {"id": user_id})
        await session.commit()
    async with test_sessionmaker() as session:
        assert await bot.linked_context(session, TELEGRAM_USER) is None
