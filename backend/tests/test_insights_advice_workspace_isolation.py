"""Insights and advice must only derive signals from the selected workspace."""
import calendar
from datetime import date, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import text

from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


def _month_date(months_ago: int) -> str:
    today = date.today()
    month_index = today.year * 12 + today.month - 1 - months_ago
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1])).isoformat()


async def _create_account(client: AsyncClient, headers: dict[str, str], name: str) -> int:
    response = await client.post(
        "/accounts", json={"name": name, "type": "cash", "currency": "KZT"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_category(client: AsyncClient, headers: dict[str, str], name: str, kind: str) -> int:
    response = await client.post(
        "/categories",
        json={"name": name, "kind": kind, "color": "#2a78d6"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _post_transaction(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    account_id: int,
    category_id: int,
    kind: str,
    amount: str,
    when: str,
) -> None:
    response = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "type": kind,
            "amount": amount,
            "description": "workspace isolation source",
            "date": when,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def test_authenticated_insights_and_advice_ignore_other_workspace_financial_state(
    workspace_client: AsyncClient, test_sessionmaker
):
    user_id, first_workspace = await _bootstrap_user(test_sessionmaker, "insights-owner@example.com")
    second_workspace = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:id, 'household', 'Second', :user)"),
            {"id": second_workspace, "user": user_id},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :workspace, :user, 'owner')"),
            {"id": uuid4(), "workspace": second_workspace, "user": user_id},
        )
        await session.commit()

    csrf = await _login(workspace_client, "insights-owner@example.com")
    second_headers = _write_headers(csrf, second_workspace)
    first_headers = {"X-Aurum-Workspace": str(first_workspace)}

    idle_account = await _create_account(workspace_client, second_headers, "Second idle cash")
    income_category = await _create_category(workspace_client, second_headers, "Second income", "income")
    await _post_transaction(
        workspace_client,
        second_headers,
        account_id=idle_account,
        category_id=income_category,
        kind="income",
        amount="5000.00",
        when=(date.today() - timedelta(days=400)).isoformat(),
    )

    spending_account = await _create_account(workspace_client, second_headers, "Second spending")
    spending_category_name = "Second rising spending"
    spending_category = await _create_category(workspace_client, second_headers, spending_category_name, "expense")
    for months_ago in (3, 2, 1):
        await _post_transaction(
            workspace_client,
            second_headers,
            account_id=spending_account,
            category_id=spending_category,
            kind="expense",
            amount="10.00",
            when=_month_date(months_ago),
        )
    await _post_transaction(
        workspace_client,
        second_headers,
        account_id=spending_account,
        category_id=spending_category,
        kind="expense",
        amount="30.00",
        when=_month_date(0),
    )
    budget = await workspace_client.post(
        "/budgets", json={"category_id": spending_category, "monthly_limit": "10.00"}, headers=second_headers
    )
    assert budget.status_code == 201, budget.text

    first_alerts = await workspace_client.get("/insights/alerts", headers=first_headers)
    first_advice = await workspace_client.get("/advice", headers=first_headers)
    second_alerts = await workspace_client.get("/insights/alerts", headers=second_headers)
    second_advice = await workspace_client.get("/advice", headers=second_headers)
    assert (first_alerts.status_code, first_advice.status_code, second_alerts.status_code, second_advice.status_code) == (200, 200, 200, 200)

    assert {alert["key"] for alert in first_alerts.json()["alerts"]}.isdisjoint({"idle_cash", "budget_exceeded"})
    assert first_advice.json()["items"] == []
    assert {alert["key"] for alert in second_alerts.json()["alerts"]} >= {"idle_cash", "budget_exceeded"}
    assert any(
        item["key"] == "rising_category" and item["params"]["category"] == spending_category_name
        for item in second_advice.json()["items"]
    )


async def test_authenticated_insights_and_advice_hide_legacy_rows_but_auth_disabled_sees_them(
    client: AsyncClient, workspace_client: AsyncClient, test_sessionmaker
):
    idle_account = (await client.post("/accounts", json={"name": "Legacy idle", "type": "cash", "currency": "KZT"})).json()["id"]
    income_category = (await client.post(
        "/categories", json={"name": "Legacy income", "kind": "income", "color": "#2a78d6"}
    )).json()["id"]
    expense_category_name = "Legacy rising spending"
    expense_category = (await client.post(
        "/categories", json={"name": expense_category_name, "kind": "expense", "color": "#2a78d6"}
    )).json()["id"]
    spending_account = (await client.post(
        "/accounts", json={"name": "Legacy spending", "type": "cash", "currency": "KZT"}
    )).json()["id"]

    await _post_transaction(
        client,
        {},
        account_id=idle_account,
        category_id=income_category,
        kind="income",
        amount="5000.00",
        when=(date.today() - timedelta(days=400)).isoformat(),
    )
    for months_ago in (3, 2, 1):
        await _post_transaction(
            client,
            {},
            account_id=spending_account,
            category_id=expense_category,
            kind="expense",
            amount="10.00",
            when=_month_date(months_ago),
        )
    await _post_transaction(
        client,
        {},
        account_id=spending_account,
        category_id=expense_category,
        kind="expense",
        amount="30.00",
        when=_month_date(0),
    )

    _, workspace_id = await _bootstrap_user(test_sessionmaker, "legacy-hidden@example.com")
    csrf = await _login(workspace_client, "legacy-hidden@example.com")
    headers = _write_headers(csrf, workspace_id)

    scoped_alerts = await workspace_client.get("/insights/alerts", headers=headers)
    scoped_advice = await workspace_client.get("/advice", headers=headers)
    legacy_alerts = await client.get("/insights/alerts")
    legacy_advice = await client.get("/advice")
    assert (scoped_alerts.status_code, scoped_advice.status_code, legacy_alerts.status_code, legacy_advice.status_code) == (200, 200, 200, 200)

    assert "idle_cash" not in {alert["key"] for alert in scoped_alerts.json()["alerts"]}
    assert scoped_advice.json()["items"] == []
    assert "idle_cash" in {alert["key"] for alert in legacy_alerts.json()["alerts"]}
    assert any(
        item["key"] == "rising_category" and item["params"]["category"] == expense_category_name
        for item in legacy_advice.json()["items"]
    )
