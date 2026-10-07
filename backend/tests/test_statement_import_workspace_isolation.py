"""Workspace boundaries for statement-import commits."""
from uuid import uuid4

from sqlalchemy import text

from tests.test_asset_crypto_investment_workspace_isolation import _second_workspace
from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


def _payload(account_id: int, *, category_id: int | None = None, external_id: str = "statement-row") -> dict:
    row = {
        "source_row": "row 1",
        "date": "2026-10-07",
        "type": "expense",
        "amount": "10.00",
        "account_currency": "KZT",
        "currency": "KZT",
        "transaction_amount": "10.00",
        "description": "Statement row",
        "external_id": external_id,
    }
    if category_id is not None:
        row["category_id"] = category_id
    return {"provider": "test", "accounts_by_currency": {"KZT": account_id}, "rows": [row]}


async def _account(client, headers: dict[str, str], name: str) -> dict:
    response = await client.post(
        "/accounts", json={"name": name, "type": "cash", "currency": "KZT"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _category(client, headers: dict[str, str], name: str, kind: str = "expense") -> dict:
    response = await client.post(
        "/categories", json={"name": name, "kind": kind, "color": "#2a78d6"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _transaction_count(maker) -> int:
    async with maker() as session:
        return (await session.execute(text("SELECT count(*) FROM transactions"))).scalar_one()


async def test_authenticated_statement_import_cannot_use_foreign_account_or_category(workspace_client, test_sessionmaker):
    user_id, workspace_a = await _bootstrap_user(test_sessionmaker, "statement-owner@example.com")
    workspace_b = await _second_workspace(test_sessionmaker, user_id)
    csrf = await _login(workspace_client, "statement-owner@example.com")
    headers_a = _write_headers(csrf, workspace_a)
    headers_b = _write_headers(csrf, workspace_b)
    account_a = await _account(workspace_client, headers_a, "A account")
    account_b = await _account(workspace_client, headers_b, "B account")
    category_b = await _category(workspace_client, headers_b, "B category")

    foreign_account = await workspace_client.post(
        "/statement-imports/commit", json=_payload(account_b["id"], external_id="foreign-account"), headers=headers_a
    )
    foreign_category = await workspace_client.post(
        "/statement-imports/commit",
        json=_payload(account_a["id"], category_id=category_b["id"], external_id="foreign-category"),
        headers=headers_a,
    )

    assert foreign_account.status_code == 404
    assert foreign_category.status_code == 404
    assert await _transaction_count(test_sessionmaker) == 0


async def test_authenticated_statement_import_hides_legacy_references_and_stamps_workspace(
    workspace_client, test_sessionmaker
):
    _, workspace_a = await _bootstrap_user(test_sessionmaker, "statement-legacy@example.com")
    csrf = await _login(workspace_client, "statement-legacy@example.com")
    headers_a = _write_headers(csrf, workspace_a)
    account_a = await _account(workspace_client, headers_a, "Scoped account")
    category_a = await _category(workspace_client, headers_a, "Scoped category")

    async with test_sessionmaker() as session:
        legacy_account = (
            await session.execute(
                text(
                    "INSERT INTO accounts (workspace_id, name, type, currency, is_archived) "
                    "VALUES (NULL, 'Legacy account', 'cash', 'KZT', false) RETURNING id"
                )
            )
        ).scalar_one()
        legacy_category = (
            await session.execute(
                text(
                    "INSERT INTO categories (workspace_id, name, kind, color, sort_order, is_default) "
                    "VALUES (NULL, 'Legacy category', 'EXPENSE', '#2a78d6', 0, false) RETURNING id"
                )
            )
        ).scalar_one()
        await session.commit()

    legacy_account_response = await workspace_client.post(
        "/statement-imports/commit", json=_payload(legacy_account, external_id="legacy-account"), headers=headers_a
    )
    legacy_category_response = await workspace_client.post(
        "/statement-imports/commit",
        json=_payload(account_a["id"], category_id=legacy_category, external_id="legacy-category"),
        headers=headers_a,
    )
    success = await workspace_client.post(
        "/statement-imports/commit",
        json=_payload(account_a["id"], category_id=category_a["id"], external_id="scoped-success"),
        headers=headers_a,
    )

    assert legacy_account_response.status_code == 404
    assert legacy_category_response.status_code == 404
    assert success.status_code == 200, success.text
    async with test_sessionmaker() as session:
        workspace_id = (
            await session.execute(text("SELECT workspace_id FROM transactions WHERE external_id='scoped-success'"))
        ).scalar_one()
    assert workspace_id == workspace_a


async def test_statement_import_rejects_incompatible_category_kind(workspace_client, test_sessionmaker):
    _, workspace_a = await _bootstrap_user(test_sessionmaker, "statement-kind@example.com")
    csrf = await _login(workspace_client, "statement-kind@example.com")
    headers_a = _write_headers(csrf, workspace_a)
    account_a = await _account(workspace_client, headers_a, "A account")
    income_category = await _category(workspace_client, headers_a, "Income category", kind="income")

    response = await workspace_client.post(
        "/statement-imports/commit",
        json=_payload(account_a["id"], category_id=income_category["id"], external_id="wrong-kind"),
        headers=headers_a,
    )

    assert response.status_code == 400
    assert await _transaction_count(test_sessionmaker) == 0


async def test_auth_disabled_statement_import_remains_global(client, account_id):
    response = await client.post(
        "/statement-imports/commit", json=_payload(account_id, external_id=f"legacy-{uuid4()}"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"created": 1, "duplicates": 0, "ignored": 0}
