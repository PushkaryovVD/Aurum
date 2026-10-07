"""Workspace isolation for cash-flow and net-worth reporting."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from tests.helpers import money
from tests.test_asset_crypto_investment_workspace_isolation import _second_workspace
from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


async def _report_data(client, headers: dict[str, str], suffix: str, income: str, expense: str, asset_value: str) -> None:
    account = await client.post(
        "/accounts",
        json={"name": f"Cash {suffix}", "type": "cash", "currency": "KZT"},
        headers=headers,
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]
    for transaction_type, amount in (("income", income), ("expense", expense)):
        response = await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": transaction_type,
                "amount": amount,
                "description": f"{transaction_type} {suffix}",
                "date": "2026-01-15",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
    asset = await client.post(
        "/assets",
        json={
            "name": f"Asset {suffix}",
            "asset_class": "other",
            "currency": "KZT",
            "value": asset_value,
            "as_of_date": "2026-01-15",
            "exchange_rate_to_kzt": "1",
        },
        headers=headers,
    )
    assert asset.status_code == 201, asset.text


async def test_cash_flow_and_net_worth_are_workspace_scoped(workspace_client, test_sessionmaker):
    user_id, workspace_a = await _bootstrap_user(test_sessionmaker, "reports-owner@example.com")
    workspace_b = await _second_workspace(test_sessionmaker, user_id, "Reports B")
    csrf = await _login(workspace_client, "reports-owner@example.com")
    headers_a = _write_headers(csrf, workspace_a)
    headers_b = _write_headers(csrf, workspace_b)

    await _report_data(workspace_client, headers_a, "A", "100.00", "30.00", "400.00")
    await _report_data(workspace_client, headers_b, "B", "900.00", "100.00", "7000.00")

    read_a = {"X-Aurum-Workspace": str(workspace_a)}
    read_b = {"X-Aurum-Workspace": str(workspace_b)}
    cash_a = (await workspace_client.get("/cash-flow", headers=read_a)).json()
    cash_b = (await workspace_client.get("/cash-flow", headers=read_b)).json()
    net_worth_a = (await workspace_client.get("/net-worth/summary", params={"range": "all"}, headers=read_a)).json()
    net_worth_b = (await workspace_client.get("/net-worth/summary", params={"range": "all"}, headers=read_b)).json()

    assert money(cash_a["total_income"]) == Decimal("100.00")
    assert money(cash_a["total_expense"]) == Decimal("30.00")
    assert money(cash_b["total_income"]) == Decimal("900.00")
    assert money(cash_b["total_expense"]) == Decimal("100.00")
    assert money(net_worth_a["current"]) == Decimal("470.00")
    assert money(net_worth_b["current"]) == Decimal("7800.00")


async def test_authenticated_reports_hide_legacy_rows_but_auth_disabled_reports_remain_global(
    client, workspace_client, test_sessionmaker
):
    legacy_account = await client.post(
        "/accounts", json={"name": "Legacy cash", "type": "cash", "currency": "KZT"}
    )
    assert legacy_account.status_code == 201, legacy_account.text
    legacy_transaction = await client.post(
        "/transactions",
        json={
            "account_id": legacy_account.json()["id"],
            "type": "income",
            "amount": "500.00",
            "description": "Legacy income",
            "date": "2026-01-15",
        },
    )
    assert legacy_transaction.status_code == 201, legacy_transaction.text
    legacy_asset = await client.post(
        "/assets",
        json={
            "name": "Legacy asset",
            "asset_class": "other",
            "currency": "KZT",
            "value": "2000.00",
            "as_of_date": "2026-01-15",
            "exchange_rate_to_kzt": "1",
        },
    )
    assert legacy_asset.status_code == 201, legacy_asset.text

    _, workspace_a = await _bootstrap_user(test_sessionmaker, "reports-legacy@example.com")
    csrf = await _login(workspace_client, "reports-legacy@example.com")
    headers_a = _write_headers(csrf, workspace_a)
    await _report_data(workspace_client, headers_a, "Scoped", "100.00", "20.00", "300.00")

    scoped_headers = {"X-Aurum-Workspace": str(workspace_a)}
    scoped_cash = (await workspace_client.get("/cash-flow", headers=scoped_headers)).json()
    scoped_net_worth = (
        await workspace_client.get("/net-worth/summary", params={"range": "all"}, headers=scoped_headers)
    ).json()
    legacy_cash = (await client.get("/cash-flow")).json()
    legacy_net_worth = (await client.get("/net-worth/summary", params={"range": "all"})).json()

    assert money(scoped_cash["total_income"]) == Decimal("100.00")
    assert money(scoped_cash["total_expense"]) == Decimal("20.00")
    assert money(scoped_net_worth["current"]) == Decimal("380.00")
    assert money(legacy_cash["total_income"]) == Decimal("600.00")
    assert money(legacy_cash["total_expense"]) == Decimal("20.00")
    assert money(legacy_net_worth["current"]) == Decimal("2880.00")
