"""Cash flow: month-by-month income vs. expense across an explicit date
range, or the full transaction history when no range is given.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def test_explicit_range_excludes_transactions_outside_it(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    salary_id = categories["Salary"]["id"]
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="1000.00", type="income", category_id=salary_id, date="2022-05-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="9999.00", type="income", category_id=salary_id, date="2021-01-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="9999.00", type="income", category_id=salary_id, date="2023-01-01")
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-01-01", "end_date": "2022-12-31"})
    body = resp.json()
    assert money(body["total_income"]) == Decimal("1000.00")
    assert len(body["points"]) == 12  # every month of 2022, including zero months
    assert body["start_date"] == "2022-01-01"
    assert body["end_date"] == "2022-12-31"


async def test_transfers_are_excluded_from_totals(client: AsyncClient, account_id):
    other = await client.post("/accounts", json={"name": "Savings", "type": "savings", "currency": "USD"})
    other_id = other.json()["id"]
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="transfer",
            amount="500.00",
            transfer_amount="1.00",
            transfer_account_id=other_id,
            date="2022-03-01",
        ),
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-01-01", "end_date": "2022-12-31"})
    body = resp.json()
    assert money(body["total_income"]) == 0
    assert money(body["total_expense"]) == 0


async def test_no_range_falls_back_to_earliest_and_latest_transaction_dates(
    client: AsyncClient, account_id, categories
):
    category_id = categories["Groceries"]["id"]
    await client.post("/transactions", json=txn_payload(account_id, category_id=category_id, date="2021-06-15"))
    await client.post("/transactions", json=txn_payload(account_id, category_id=category_id, date="2024-02-10"))

    resp = await client.get("/cash-flow")
    body = resp.json()
    assert body["start_date"] == "2021-06-15"
    assert body["end_date"] == "2024-02-10"


async def test_no_transactions_returns_empty_points_and_null_bounds(client: AsyncClient):
    resp = await client.get("/cash-flow")
    body = resp.json()
    assert body["points"] == []
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert money(body["total_net"]) == 0


async def test_monthly_points_split_income_and_expense_correctly(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    salary_id = categories["Salary"]["id"]
    await client.post(
        "/transactions", json=txn_payload(account_id, type="income", amount="2000.00", category_id=salary_id, date="2022-04-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, type="expense", amount="300.00", category_id=category_id, date="2022-04-15")
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-04-01", "end_date": "2022-04-30"})
    point = resp.json()["points"][0]
    assert point["year"] == 2022
    assert point["month"] == 4
    assert money(point["income"]) == Decimal("2000.00")
    assert money(point["expense"]) == Decimal("300.00")
    assert money(point["net"]) == Decimal("1700.00")
