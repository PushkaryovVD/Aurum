"""Aggregates are reported in the workspace currency, not in raw KZT.

The ledger sums in KZT (`base_amount_kzt`); a workspace reporting in USD must
see those sums converted at the official rate for the end of each period —
and, without a rate, an honest "incomplete" instead of a KZT figure wearing a
dollar sign. Rates are seeded straight into `exchange_rates`, so nothing here
reaches the network.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from httpx import AsyncClient

from app.models.exchange_rate import ExchangeRate
from tests.helpers import money, txn_payload as _txn


async def _seed_rate(test_sessionmaker, currency: str, rate: str, as_of: date) -> None:
    async with test_sessionmaker() as session:
        session.add(
            ExchangeRate(
                requested_date=as_of,
                effective_date=as_of,
                currency=currency,
                rate_to_kzt=Decimal(rate),
                source="manual",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _set_currency(client: AsyncClient, currency: str) -> None:
    response = await client.patch("/settings", json={"currency": currency})
    assert response.status_code == 200, response.text


async def _august_ledger(client: AsyncClient, account_id: int, categories: dict) -> None:
    """August 2026: 3,000,000 KZT + 1,000 USD (manual rate 450) of salary, and
    500,000 KZT of groceries."""
    salary = categories["Salary"]["id"]
    groceries = categories["Groceries"]["id"]
    usd_account = (
        await client.post("/accounts", json={"name": "USD card", "type": "debit_card", "currency": "USD"})
    ).json()["id"]
    for payload in (
        _txn(account_id, type="income", amount="3000000.00", category_id=salary, date="2026-08-05"),
        _txn(
            usd_account, type="income", amount="1000.00", category_id=salary, date="2026-08-10",
            exchange_rate_to_kzt="450",
        ),
        _txn(account_id, type="expense", amount="500000.00", category_id=groceries, date="2026-08-20"),
    ):
        response = await client.post("/transactions", json=payload)
        assert response.status_code == 201, response.text


def _no_network(monkeypatch) -> None:
    async def _unavailable(*args, **kwargs):
        raise HTTPException(status_code=503, detail="NBK unavailable")

    monkeypatch.setattr("app.services.reporting_currency.get_exchange_rate", _unavailable)
    monkeypatch.setattr("app.services.dashboard_service.get_exchange_rate", _unavailable)


async def test_usd_workspace_dashboard_converts_at_the_month_end_rate(
    client: AsyncClient, test_sessionmaker, account_id, categories, monkeypatch
):
    _no_network(monkeypatch)
    # An early-month rate must not be used for a month total: the month's
    # last day decides.
    await _seed_rate(test_sessionmaker, "USD", "450", date(2026, 8, 1))
    await _seed_rate(test_sessionmaker, "USD", "500", date(2026, 8, 31))
    await _set_currency(client, "USD")
    await _august_ledger(client, account_id, categories)

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8})).json()

    assert body["reporting_currency"] == "USD"
    assert body["incomplete"] is False
    # (3,000,000 + 1,000 * 450) / 500 and 500,000 / 500
    assert money(body["real_income"]) == Decimal("6900.00")
    assert money(body["spent"]) == Decimal("1000.00")
    assert money(body["net"]) == Decimal("5900.00")
    groceries = next(item for item in body["spending_by_category"] if item["name"] == "Groceries")
    assert money(groceries["amount"]) == Decimal("1000.00")
    assert groceries["percent"] == 100.0
    # The balance card already reported in USD; it still does (the USD card
    # counts at its own 1,000 USD, the KZT account at today's rate).
    assert body["balance"]["reporting_currency"] == "USD"
    assert money(body["balance"]["total"]) == Decimal("6000.00")


async def test_usd_workspace_reports_budgets_and_envelopes_share_the_currency(
    client: AsyncClient, test_sessionmaker, account_id, categories, monkeypatch
):
    _no_network(monkeypatch)
    await _seed_rate(test_sessionmaker, "USD", "500", date(2026, 8, 31))
    await _set_currency(client, "USD")
    await _august_ledger(client, account_id, categories)
    groceries = categories["Groceries"]["id"]

    cash_flow = (
        await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    ).json()
    assert cash_flow["reporting_currency"] == "USD"
    assert cash_flow["incomplete"] is False
    assert [(money(p["income"]), money(p["expense"]), money(p["net"])) for p in cash_flow["points"]] == [
        (Decimal("6900.00"), Decimal("1000.00"), Decimal("5900.00"))
    ]
    assert money(cash_flow["total_net"]) == Decimal("5900.00")

    ranking = (
        await client.get(
            "/reports/category-ranking",
            params={"kind": "expense", "start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
    ).json()
    assert ranking["reporting_currency"] == "USD"
    assert money(ranking["total_amount"]) == Decimal("1000.00")

    spending = (
        await client.get(
            "/reports/category-spending",
            params={"category_id": groceries, "start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
    ).json()
    assert spending["reporting_currency"] == "USD"
    assert money(spending["total_amount"]) == Decimal("1000.00")
    assert [money(point["amount"]) for point in spending["series"]] == [Decimal("1000.00")]

    # The limit is typed in USD; spend is compared in USD, not in KZT.
    assert (await client.post("/budgets", json={"category_id": groceries, "monthly_limit": "800"})).status_code == 201
    status = (await client.get("/budgets/status", params={"year": 2026, "month": 8})).json()
    assert status["reporting_currency"] == "USD"
    item = status["items"][0]
    assert money(item["spent"]) == Decimal("1000.00")
    assert money(item["remaining"]) == Decimal("-200.00")
    assert item["is_over_budget"] is True

    envelope = (await client.post("/envelopes/2026/8/open")).json()
    assert envelope["reporting_currency"] == "USD"
    assert envelope["fx_incomplete"] is False
    assert money(envelope["income"]) == Decimal("6900.00")
    assert money(envelope["available_to_assign"]) == Decimal("6900.00")

    net_worth = (await client.get("/net-worth/summary", params={"range": "all"})).json()
    assert net_worth["reporting_currency"] == "USD"
    assert net_worth["incomplete"] is False
    # Today is after 2026-08-31, so today's rate is the latest cached one.
    assert money(net_worth["current"]) == Decimal("5900.00")
    cash = next(item for item in net_worth["breakdown"] if item["key"] == "cash")
    assert money(cash["amount"]) == Decimal("5900.00")


async def test_kzt_workspace_amounts_are_the_ledger_sums_untouched(
    client: AsyncClient, account_id, categories, monkeypatch
):
    _no_network(monkeypatch)
    await _set_currency(client, "KZT")
    salary = categories["Salary"]["id"]
    groceries = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, type="income", amount="1234.57", category_id=salary, date="2026-08-05"))
    await client.post("/transactions", json=_txn(account_id, type="expense", amount="0.01", category_id=groceries, date="2026-08-06"))

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8})).json()
    assert body["reporting_currency"] == "KZT"
    assert body["incomplete"] is False
    assert money(body["real_income"]) == Decimal("1234.57")
    assert money(body["spent"]) == Decimal("0.01")
    assert money(body["net"]) == Decimal("1234.56")

    cash_flow = (
        await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    ).json()
    assert cash_flow["reporting_currency"] == "KZT"
    assert money(cash_flow["total_income"]) == Decimal("1234.57")


async def test_missing_rate_is_reported_as_incomplete_not_as_a_number(
    client: AsyncClient, account_id, categories, monkeypatch
):
    _no_network(monkeypatch)
    # No EUR rate is cached and NBK is unreachable.
    await _set_currency(client, "EUR")
    groceries = categories["Groceries"]["id"]
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date="2026-08-05"),
    )
    await client.post("/transactions", json=_txn(account_id, type="expense", amount="700.00", category_id=groceries, date="2026-08-06"))

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8})).json()
    assert body["reporting_currency"] == "EUR"
    assert body["incomplete"] is True
    assert body["real_income"] is None
    assert body["spent"] is None
    assert body["net"] is None
    assert body["spending_by_category"][0]["amount"] is None
    # The share is a ratio of KZT sums and stays exact.
    assert body["spending_by_category"][0]["percent"] == 100.0

    cash_flow = (
        await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    ).json()
    assert cash_flow["incomplete"] is True
    assert cash_flow["points"][0]["income"] is None

    assert (await client.post("/budgets", json={"category_id": groceries, "monthly_limit": "1"})).status_code == 201
    status = (await client.get("/budgets/status", params={"year": 2026, "month": 8})).json()
    assert status["incomplete"] is True
    assert status["items"][0]["spent"] is None
    # Unknown spend is never called "over budget".
    assert status["items"][0]["is_over_budget"] is False

    net_worth = (await client.get("/net-worth/summary", params={"range": "30d"})).json()
    assert net_worth["incomplete"] is True
    assert net_worth["current"] is None
