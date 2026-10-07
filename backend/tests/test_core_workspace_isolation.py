"""Workspace isolation for the bounded core financial slice."""
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_finance_access
from app.core.config import Settings
from app.main import create_app
from app.models.transaction import Transaction
from app.security.auth import PasswordService

HMAC_SECRET = "workspace-scope-test-secret-with-at-least-32-bytes"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def workspace_auth_settings() -> Settings:
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
async def workspace_client(test_sessionmaker, workspace_auth_settings) -> AsyncGenerator[AsyncClient, None]:
    scoped_app = create_app(workspace_auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    async def allow_finance_for_isolation_tests() -> None:
        """Exercise scoped route logic independently from the release readiness gate."""

    scoped_app.dependency_overrides[get_session] = override_get_session
    scoped_app.dependency_overrides[require_finance_access] = allow_finance_for_isolation_tests
    async with AsyncClient(
        transport=ASGITransport(app=scoped_app), base_url="https://test/api"
    ) as client:
        yield client


async def _bootstrap_user(test_sessionmaker, login: str) -> tuple[UUID, UUID]:
    user_id, workspace_id = uuid4(), uuid4()
    password_hash = PasswordService(memory_cost=8192, time_cost=1, parallelism=1).hash(PASSWORD)
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (id, normalized_login, display_name, status, password_hash)
                VALUES (:user_id, :login, :login, 'active', :password_hash)
                """
            ),
            {"user_id": user_id, "login": login, "password_hash": password_hash},
        )
        await session.execute(
            text(
                """
                INSERT INTO workspaces (id, kind, display_name, created_by_user_id, personal_owner_user_id)
                VALUES (:workspace_id, 'personal', :login, :user_id, :user_id)
                """
            ),
            {"workspace_id": workspace_id, "login": login, "user_id": user_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
                VALUES (:id, :workspace_id, :user_id, 'owner')
                """
            ),
            {"id": uuid4(), "workspace_id": workspace_id, "user_id": user_id},
        )
        await session.execute(
            text("UPDATE users SET personal_workspace_id=:workspace_id WHERE id=:user_id"),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        await session.commit()
    return user_id, workspace_id


async def _login(client: AsyncClient, login: str) -> str:
    response = await client.post(
        "/auth/session",
        json={"identifier": login, "password": PASSWORD},
        headers={"Origin": "https://test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _write_headers(csrf: str, workspace_id: UUID) -> dict[str, str]:
    return {
        "X-CSRF-Token": csrf,
        "X-Aurum-Workspace": str(workspace_id),
        "Origin": "https://test",
    }


async def _create_core_records(client: AsyncClient, csrf: str, workspace_id: UUID, suffix: str) -> dict:
    headers = _write_headers(csrf, workspace_id)
    account = await client.post(
        "/accounts", json={"name": f"Account {suffix}", "type": "cash", "currency": "KZT"}, headers=headers
    )
    category = await client.post(
        "/categories",
        json={"name": f"Category {suffix}", "kind": "expense", "color": "#2a78d6"},
        headers=headers,
    )
    tag = await client.post("/tags", json={"name": f"Tag {suffix}"}, headers=headers)
    assert (account.status_code, category.status_code, tag.status_code) == (201, 201, 201)
    transaction = await client.post(
        "/transactions",
        json={
            "account_id": account.json()["id"],
            "category_id": category.json()["id"],
            "tag_ids": [tag.json()["id"]],
            "type": "expense",
            "amount": "0.01",
            "description": f"Transaction {suffix}",
            "date": "2026-01-15",
        },
        headers=headers,
    )
    assert transaction.status_code == 201, transaction.text
    return {
        "account": account.json(),
        "category": category.json(),
        "tag": tag.json(),
        "transaction": transaction.json(),
    }


async def test_core_lists_and_mutations_are_workspace_scoped(
    workspace_client, test_sessionmaker
):
    user_id, first_workspace = await _bootstrap_user(test_sessionmaker, "owner@example.com")
    second_workspace = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO workspaces (id, kind, display_name, created_by_user_id)
                VALUES (:workspace_id, 'household', 'Second', :user_id)
                """
            ),
            {"workspace_id": second_workspace, "user_id": user_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
                VALUES (:id, :workspace_id, :user_id, 'owner')
                """
            ),
            {"id": uuid4(), "workspace_id": second_workspace, "user_id": user_id},
        )
        await session.commit()

    csrf = await _login(workspace_client, "owner@example.com")
    first = await _create_core_records(workspace_client, csrf, first_workspace, "first")
    second = await _create_core_records(workspace_client, csrf, second_workspace, "second")

    first_headers = {"X-Aurum-Workspace": str(first_workspace)}
    assert [row["id"] for row in (await workspace_client.get("/accounts", headers=first_headers)).json()] == [
        first["account"]["id"]
    ]
    assert [row["id"] for row in (await workspace_client.get("/categories", headers=first_headers)).json()] == [
        first["category"]["id"]
    ]
    assert [row["id"] for row in (await workspace_client.get("/tags", headers=first_headers)).json()] == [
        first["tag"]["id"]
    ]
    tx_page = (await workspace_client.get("/transactions", headers=first_headers)).json()
    assert [row["id"] for row in tx_page["items"]] == [first["transaction"]["id"]]
    assert tx_page["items"][0]["author_user_id"] == str(user_id)

    write_headers = _write_headers(csrf, first_workspace)
    assert (
        await workspace_client.patch(
            f"/accounts/{second['account']['id']}", json={"name": "probe"}, headers=write_headers
        )
    ).status_code == 404
    assert (
        await workspace_client.delete(f"/categories/{second['category']['id']}", headers=write_headers)
    ).status_code == 404
    assert (
        await workspace_client.delete(f"/tags/{second['tag']['id']}", headers=write_headers)
    ).status_code == 404
    assert (
        await workspace_client.patch(
            f"/transactions/{second['transaction']['id']}", json={"description": "probe"}, headers=write_headers
        )
    ).status_code == 404


async def test_foreign_transaction_references_are_rejected_without_disclosure(
    workspace_client, test_sessionmaker
):
    user_id, first_workspace = await _bootstrap_user(test_sessionmaker, "refs@example.com")
    second_workspace = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:id, 'household', 'Other', :user)"),
            {"id": second_workspace, "user": user_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'owner')"),
            {"id": uuid4(), "workspace": second_workspace, "user": user_id},
        )
        await session.commit()
    csrf = await _login(workspace_client, "refs@example.com")
    first = await _create_core_records(workspace_client, csrf, first_workspace, "local")
    foreign = await _create_core_records(workspace_client, csrf, second_workspace, "foreign")
    headers = _write_headers(csrf, first_workspace)
    base = {
        "account_id": first["account"]["id"],
        "category_id": first["category"]["id"],
        "type": "expense",
        "amount": "1.00",
        "description": "Probe",
        "date": "2026-01-15",
    }
    for change in (
        {"account_id": foreign["account"]["id"]},
        {"category_id": foreign["category"]["id"]},
        {"tag_ids": [foreign["tag"]["id"]]},
        {
            "type": "transfer",
            "category_id": None,
            "transfer_account_id": foreign["account"]["id"],
        },
        {
            "category_id": None,
            "amount": "2.00",
            "splits": [
                {"category_id": first["category"]["id"], "amount": "1.00"},
                {"category_id": foreign["category"]["id"], "amount": "1.00"},
            ],
        },
    ):
        response = await workspace_client.post("/transactions", json={**base, **change}, headers=headers)
        assert response.status_code == 400, response.text


async def test_viewer_can_read_but_cannot_mutate(workspace_client, test_sessionmaker):
    owner_id, _ = await _bootstrap_user(test_sessionmaker, "owner2@example.com")
    viewer_id, _ = await _bootstrap_user(test_sessionmaker, "viewer@example.com")
    workspace_id = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:id, 'household', 'Shared', :owner)"),
            {"id": workspace_id, "owner": owner_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'owner')"),
            {"id": uuid4(), "workspace": workspace_id, "user": owner_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'viewer')"),
            {"id": uuid4(), "workspace": workspace_id, "user": viewer_id},
        )
        await session.commit()
    csrf = await _login(workspace_client, "owner2@example.com")
    await _create_core_records(workspace_client, csrf, workspace_id, "shared")
    workspace_client.cookies.clear()
    viewer_csrf = await _login(workspace_client, "viewer@example.com")
    headers = _write_headers(viewer_csrf, workspace_id)
    assert (await workspace_client.get("/accounts", headers=headers)).status_code == 200
    denied = await workspace_client.post(
        "/accounts", json={"name": "Denied", "type": "cash", "currency": "KZT"}, headers=headers
    )
    assert denied.status_code == 403


async def test_editor_can_mutate_shared_workspace(workspace_client, test_sessionmaker):
    owner_id, _ = await _bootstrap_user(test_sessionmaker, "shared-owner@example.com")
    editor_id, _ = await _bootstrap_user(test_sessionmaker, "shared-editor@example.com")
    workspace_id = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:id, 'household', 'Shared editor', :owner)"),
            {"id": workspace_id, "owner": owner_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'owner')"),
            {"id": uuid4(), "workspace": workspace_id, "user": owner_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'editor')"),
            {"id": uuid4(), "workspace": workspace_id, "user": editor_id},
        )
        await session.commit()

    csrf = await _login(workspace_client, "shared-editor@example.com")
    records = await _create_core_records(workspace_client, csrf, workspace_id, "editor")
    assert records["transaction"]["author_user_id"] == str(editor_id)


async def test_non_member_cannot_select_another_users_workspace(workspace_client, test_sessionmaker):
    _, first_workspace = await _bootstrap_user(test_sessionmaker, "first-member@example.com")
    _, foreign_workspace = await _bootstrap_user(test_sessionmaker, "foreign-member@example.com")
    csrf = await _login(workspace_client, "first-member@example.com")

    read = await workspace_client.get(
        "/accounts", headers={"X-Aurum-Workspace": str(foreign_workspace)}
    )
    write = await workspace_client.post(
        "/accounts",
        json={"name": "Denied", "type": "cash", "currency": "KZT"},
        headers=_write_headers(csrf, foreign_workspace),
    )
    assert read.status_code == 404
    assert write.status_code == 404

    own = await workspace_client.get(
        "/accounts", headers={"X-Aurum-Workspace": str(first_workspace)}
    )
    assert own.status_code == 200


async def test_auth_disabled_keeps_legacy_unscoped_behavior_and_zero_decimal(
    client: AsyncClient, test_sessionmaker, account_id, categories
):
    destination = (await client.post("/accounts", json={"name": "Zero", "type": "cash", "currency": "KZT"})).json()
    async with test_sessionmaker() as session:
        transaction = Transaction(
            account_id=account_id,
            transfer_account_id=destination["id"],
            type="transfer",
            amount=Decimal("10.00"),
            transfer_amount=Decimal("0.00"),
            currency="KZT",
            transaction_amount=Decimal("10.00"),
            description="Zero destination amount",
            date=date(2026, 1, 15),
        )
        session.add(transaction)
        await session.commit()
    accounts = {row["id"]: row for row in (await client.get("/accounts")).json()}
    assert Decimal(str(accounts[account_id]["balance"])) == Decimal("-10.00")
    assert Decimal(str(accounts[destination["id"]]["balance"])) == Decimal("0.00")


async def test_workspace_mode_disables_installation_wide_backup(
    client: AsyncClient, workspace_client: AsyncClient, test_sessionmaker
):
    legacy_export = await client.get("/backup/export")
    assert legacy_export.status_code == 200
    account_count = len((await client.get("/accounts")).json())

    _, workspace_id = await _bootstrap_user(test_sessionmaker, "backup-owner@example.com")
    csrf = await _login(workspace_client, "backup-owner@example.com")
    headers = _write_headers(csrf, workspace_id)

    export_response = await workspace_client.get("/backup/export", headers=headers)
    import_response = await workspace_client.post(
        "/backup/import", json=legacy_export.json(), headers=headers
    )

    assert export_response.status_code == 503
    assert import_response.status_code == 503
    assert export_response.json() == {"detail": "Workspace backup unavailable"}
    assert import_response.json() == {"detail": "Workspace backup unavailable"}
    assert len((await client.get("/accounts")).json()) == account_count
