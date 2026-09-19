"""Account-type behavior shared by the accounts API and financial summaries."""
from datetime import date

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def test_debit_card_is_a_liquid_account_type(client: AsyncClient, categories):
    response = await client.post(
        "/accounts",
        json={"name": "Debit card", "type": "debit_card", "currency": "RUB"},
    )

    assert response.status_code == 201
    debit_card = response.json()
    assert debit_card["type"] == "debit_card"

    transaction = await client.post(
        "/transactions",
        json=txn_payload(
            debit_card["id"],
            type="income",
            amount="1000.00",
            exchange_rate_to_kzt="1",
            exchange_rate_source="manual",
            category_id=categories["Salary"]["id"],
            date=date.today().isoformat(),
        ),
    )
    assert transaction.status_code == 201

    summary = await client.get("/net-worth/summary", params={"range": "all"})

    assert summary.status_code == 200
    assert money(summary.json()["current"]) == money("1000.00")


async def test_create_account_persists_its_currency(client: AsyncClient):
    created = await client.post("/accounts", json={"name": "USD Card", "type": "debit_card", "currency": "USD"})
    assert created.status_code == 201, created.text
    assert created.json()["currency"] == "USD"

    listed = {account["name"]: account for account in (await client.get("/accounts")).json()}
    assert listed["USD Card"]["currency"] == "USD"


async def test_account_response_carries_its_transaction_count(client: AsyncClient, account_id, categories):
    assert (await client.get("/accounts")).json()[0]["transaction_count"] == 0

    await client.post("/transactions", json=txn_payload(account_id, category_id=categories["Groceries"]["id"]))

    assert (await client.get("/accounts")).json()[0]["transaction_count"] == 1


async def test_account_currency_is_editable_while_it_has_no_transactions(client: AsyncClient):
    created = await client.post("/accounts", json={"name": "Wallet", "type": "cash", "currency": "KZT"})
    wallet_id = created.json()["id"]

    resp = await client.patch(f"/accounts/{wallet_id}", json={"currency": "EUR"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["currency"] == "EUR"


async def test_account_currency_cannot_change_once_it_has_transactions(
    client: AsyncClient, account_id, categories
):
    """Re-labelling an account would silently reinterpret the history recorded
    in its old currency (100 KZT becoming 100 USD), so it's refused outright."""
    await client.post("/transactions", json=txn_payload(account_id, category_id=categories["Groceries"]["id"]))

    resp = await client.patch(f"/accounts/{account_id}", json={"currency": "USD"})
    assert resp.status_code == 422

    assert (await client.get("/accounts")).json()[0]["currency"] == "KZT"
