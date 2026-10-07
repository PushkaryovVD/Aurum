"""Dashboard and report reads must stay inside the request workspace."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from tests.helpers import money
from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _create_core_records,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


async def test_dashboard_and_reports_exclude_foreign_and_legacy_financial_rows(
    workspace_client, client, test_sessionmaker
):
    user_id, workspace_a = await _bootstrap_user(test_sessionmaker, "dashboard-reports@example.com")
    workspace_b = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO workspaces (id, kind, display_name, created_by_user_id) "
                "VALUES (:id, 'household', 'Dashboard reports B', :user_id)"
            ),
            {"id": workspace_b, "user_id": user_id},
        )
        await session.execute(
            text(
                "INSERT INTO workspace_memberships (id, workspace_id, user_id, role) "
                "VALUES (:id, :workspace_id, :user_id, 'owner')"
            ),
            {"id": uuid4(), "workspace_id": workspace_b, "user_id": user_id},
        )
        await session.commit()

    csrf = await _login(workspace_client, "dashboard-reports@example.com")
    records_a = await _create_core_records(workspace_client, csrf, workspace_a, "dashboard A")
    records_b = await _create_core_records(workspace_client, csrf, workspace_b, "dashboard B")
    headers_a = _write_headers(csrf, workspace_a)
    headers_b = _write_headers(csrf, workspace_b)

    async with test_sessionmaker() as session:
        legacy_account_id = (
            await session.execute(text("SELECT id FROM accounts WHERE workspace_id IS NULL LIMIT 1"))
        ).scalar_one()
        legacy_category_id = (
            await session.execute(
                text(
                    "INSERT INTO categories (name, kind, color, sort_order, is_default) "
                    "VALUES ('Legacy dashboard category', 'EXPENSE', '#123456', 0, false) RETURNING id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO transactions "
                "(account_id, category_id, type, amount, currency, transaction_amount, description, date, purpose) "
                "VALUES (:account_id, :category_id, 'EXPENSE', 99, 'KZT', 99, 'Legacy dashboard transaction', "
                "'2026-01-15', 'ORDINARY')"
            ),
            {"account_id": legacy_account_id, "category_id": legacy_category_id},
        )
        await session.commit()

    dashboard_a = await workspace_client.get("/dashboard/summary?year=2026&month=1", headers=headers_a)
    dashboard_b = await workspace_client.get("/dashboard/summary?year=2026&month=1", headers=headers_b)
    assert dashboard_a.status_code == dashboard_b.status_code == 200
    assert money(dashboard_a.json()["spent"]) == Decimal("0.01")
    assert money(dashboard_b.json()["spent"]) == Decimal("0.01")
    assert [item["name"] for item in dashboard_a.json()["spending_by_category"]] == ["Category dashboard A"]
    assert [item["name"] for item in dashboard_b.json()["spending_by_category"]] == ["Category dashboard B"]

    ranking_a = await workspace_client.get("/reports/category-ranking?kind=expense", headers=headers_a)
    ranking_b = await workspace_client.get("/reports/category-ranking?kind=expense", headers=headers_b)
    assert ranking_a.status_code == ranking_b.status_code == 200
    assert money(ranking_a.json()["total_amount"]) == Decimal("0.01")
    assert money(ranking_b.json()["total_amount"]) == Decimal("0.01")
    assert [item["category_id"] for item in ranking_a.json()["items"]] == [records_a["category"]["id"]]
    assert [item["category_id"] for item in ranking_b.json()["items"]] == [records_b["category"]["id"]]

    assert (
        await workspace_client.get(
            "/reports/category-spending", params={"category_id": records_a["category"]["id"]}, headers=headers_b
        )
    ).status_code == 404
    assert (
        await workspace_client.get(
            "/reports/category-spending", params={"category_id": legacy_category_id}, headers=headers_a
        )
    ).status_code == 404

    legacy_dashboard = await client.get("/dashboard/summary?year=2026&month=1")
    legacy_ranking = await client.get("/reports/category-ranking?kind=expense")
    assert legacy_dashboard.status_code == legacy_ranking.status_code == 200
    assert money(legacy_dashboard.json()["spent"]) == Decimal("99.02")
    assert money(legacy_ranking.json()["total_amount"]) == Decimal("99.02")
