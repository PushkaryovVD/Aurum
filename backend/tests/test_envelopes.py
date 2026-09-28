"""Envelope budgeting API behavior and ledger separation."""
from decimal import Decimal

from httpx import AsyncClient
import pytest
from sqlalchemy import select

from app.models.envelope import EnvelopeAuditLog
from tests.helpers import money, txn_payload


async def _income(
    client: AsyncClient,
    account_id: int,
    category_id: int | None,
    amount: str,
    date: str,
) -> int:
    response = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="income",
            category_id=category_id,
            amount=amount,
            date=date,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_open_sets_tracking_boundary_and_allocation_cannot_exceed_available_income(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    salary = categories["Salary"]["id"]
    await _income(client, account_id, salary, "100.00", "2026-08-01")

    unopened = (await client.get("/envelopes/2026/8")).json()
    assert unopened["tracking_start"] is None
    assert money(unopened["available_to_assign"]) == Decimal("0.00")

    opened = await client.post("/envelopes/2026/8/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["tracking_start"] == {"year": 2026, "month": 8}
    assert money(opened.json()["available_to_assign"]) == Decimal("100.00")

    created = await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "80.00", "planned_amount": "90.00"},
    )
    assert created.status_code == 200, created.text
    assert money(created.json()["assigned"]) == Decimal("80.00")
    assert money(created.json()["available_to_assign"]) == Decimal("20.00")

    rejected = await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "120.00"},
    )
    assert rejected.status_code == 400
    assert "available to assign" in rejected.json()["detail"]

    unchanged = (await client.get("/envelopes/2026/8")).json()
    assert money(unchanged["assigned"]) == Decimal("80.00")
    assert money(unchanged["available_to_assign"]) == Decimal("20.00")


async def test_move_is_ledger_neutral_and_audited(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    shopping = categories["Shopping"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    for category_id in (groceries, shopping):
        response = await client.put(
            f"/envelopes/2026/8/allocations/{category_id}",
            json={"assigned_amount": "50.00"},
        )
        assert response.status_code == 200, response.text

    accounts_before = (await client.get("/accounts")).json()
    budgets_before = (await client.get("/budgets/status?year=2026&month=8")).json()
    transactions_before = (await client.get("/transactions?year=2026&month=8")).json()["total"]
    moved = await client.post(
        "/envelopes/2026/8/moves",
        json={
            "from_category_id": groceries,
            "to_category_id": shopping,
            "amount": "15.00",
            "note": "reprioritize",
        },
    )
    assert moved.status_code == 201, moved.text
    rows = {row["category_id"]: row for row in moved.json()["items"]}
    assert money(rows[groceries]["assigned_amount"]) == Decimal("35.00")
    assert money(rows[shopping]["assigned_amount"]) == Decimal("65.00")
    assert money(moved.json()["income"]) == Decimal("100.00")
    assert money(moved.json()["assigned"]) == Decimal("100.00")
    assert (await client.get("/accounts")).json() == accounts_before
    assert (await client.get("/budgets/status?year=2026&month=8")).json() == budgets_before
    assert (await client.get("/transactions?year=2026&month=8")).json()["total"] == transactions_before
    audit = (await client.get("/envelopes/2026/8/audit")).json()
    assert audit[-1]["event_type"] == "move"
    assert money(audit[-1]["amount"]) == Decimal("15.00")


async def test_refund_split_and_parent_child_attribution_are_counted_once(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post(
            "/categories",
            json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries},
        )
    ).json()["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "100.00"},
    )
    split = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            amount="50.00",
            category_id=None,
            date="2026-08-10",
            splits=[
                {"category_id": groceries, "amount": "20.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )
    assert split.status_code == 201, split.text
    refund = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="income",
            category_id=sweets,
            amount="10.00",
            date="2026-08-15",
        ),
    )
    assert refund.status_code == 201, refund.text

    status = (await client.get("/envelopes/2026/8")).json()
    parent = next(row for row in status["items"] if row["category_id"] == groceries)
    assert money(parent["activity"]) == Decimal("-40.00")
    assert money(parent["available"]) == Decimal("60.00")
    assert money(status["income"]) == Decimal("100.00")


@pytest.mark.parametrize("spend,expected", [("40.00", "60.00"), ("140.00", "-40.00")])
async def test_rollover_preserves_positive_and_negative_balances_across_gap_month(
    client: AsyncClient,
    account_id: int,
    categories: dict[str, dict],
    spend: str,
    expected: str,
):
    groceries = categories["Groceries"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-01-01")
    await client.post("/envelopes/2026/1/open")
    await client.put(
        f"/envelopes/2026/1/allocations/{groceries}",
        json={
            "assigned_amount": "100.00",
            "rollover_positive": True,
            "rollover_negative": True,
        },
    )
    await client.post(
        "/transactions",
        json=txn_payload(account_id, category_id=groceries, amount=spend, date="2026-01-10"),
    )

    march = (await client.get("/envelopes/2026/3")).json()
    item = next(row for row in march["items"] if row["category_id"] == groceries)
    assert money(item["carried_in"]) == Decimal(expected)
    assert money(item["available"]) == Decimal(expected)
    assert item["has_row"] is False


async def test_closed_month_rejects_planning_but_detects_ledger_drift(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "100.00"},
    )
    closed = await client.post("/envelopes/2026/8/close")
    assert closed.status_code == 200, closed.text
    blocked = await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "90.00"},
    )
    assert blocked.status_code == 409

    transaction = await client.post(
        "/transactions",
        json=txn_payload(account_id, category_id=groceries, amount="25.00", date="2026-08-20"),
    )
    assert transaction.status_code == 201, transaction.text
    drifted = (await client.get("/envelopes/2026/8")).json()
    assert drifted["has_ledger_drift"] is True
    assert "closed_month_ledger_drift" in {warning["code"] for warning in drifted["warnings"]}

    reopened = await client.post("/envelopes/2026/8/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["is_closed"] is False
    audit_types = [event["event_type"] for event in (await client.get("/envelopes/2026/8/audit")).json()]
    assert audit_types[-2:] == ["month_closed", "month_reopened"]


async def test_template_applies_plan_only_and_fund_reports_shortfall(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    shopping = categories["Shopping"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "70.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    template = await client.post(
        "/envelopes/templates",
        json={
            "name": "Essentials",
            "items": [
                {"category_id": groceries, "planned_amount": "50.00"},
                {"category_id": shopping, "planned_amount": "50.00"},
            ],
        },
    )
    assert template.status_code == 201, template.text
    assert len((await client.get("/envelopes/templates")).json()) == 1

    applied = await client.post(f"/envelopes/2026/8/apply-template/{template.json()['id']}")
    assert applied.status_code == 200, applied.text
    assert money(applied.json()["assigned"]) == Decimal("0.00")
    funded = await client.post("/envelopes/2026/8/fund", json={})
    assert funded.status_code == 200, funded.text
    assert money(funded.json()["status"]["assigned"]) == Decimal("70.00")
    assert sum(money(row["shortfall"]) for row in funded.json()["unfunded"]) == Decimal("30.00")
    assert "underfunded" in {warning["code"] for warning in funded.json()["status"]["warnings"]}


async def test_audit_rows_are_immutable(client: AsyncClient, account_id: int, categories, test_sessionmaker):
    groceries = categories["Groceries"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "10.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "10.00"},
    )
    async with test_sessionmaker() as session:
        event = (await session.execute(select(EnvelopeAuditLog))).scalar_one()
        event.note = "tampered"
        with pytest.raises(RuntimeError, match="immutable"):
            await session.commit()
        await session.rollback()


async def test_late_income_and_unassigned_money_are_available_for_next_month(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    salary = categories["Salary"]["id"]
    await _income(client, account_id, salary, "100.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    await client.put(
        f"/envelopes/2026/8/allocations/{groceries}",
        json={"assigned_amount": "80.00", "planned_amount": "80.00"},
    )
    await _income(client, account_id, salary, "20.00", "2026-08-25")
    august = (await client.get("/envelopes/2026/8")).json()
    assert money(august["available_to_assign"]) == Decimal("40.00")

    funded = await client.post("/envelopes/2026/8/fund-next-month")
    assert funded.status_code == 200, funded.text
    september = funded.json()["status"]
    assert money(september["assigned"]) == Decimal("40.00")
    assert money(september["available_to_assign"]) == Decimal("0.00")
    assert money(september["items"][0]["planned_amount"]) == Decimal("80.00")
    assert money(funded.json()["unfunded"][0]["shortfall"]) == Decimal("40.00")


async def test_refund_without_envelope_becomes_assignable_with_warning(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    await client.post("/envelopes/2026/8/open")
    refund = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="income",
            category_id=groceries,
            amount="25.00",
            date="2026-08-15",
        ),
    )
    assert refund.status_code == 201, refund.text
    status = (await client.get("/envelopes/2026/8")).json()
    assert money(status["income"]) == Decimal("0.00")
    assert money(status["available_to_assign"]) == Decimal("25.00")
    warning = next(item for item in status["warnings"] if item["code"] == "refund_without_envelope")
    assert warning["category_id"] == groceries


async def test_recategorizing_transaction_moves_activity_between_envelopes(
    client: AsyncClient, account_id: int, categories: dict[str, dict]
):
    groceries = categories["Groceries"]["id"]
    shopping = categories["Shopping"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-08-01")
    await client.post("/envelopes/2026/8/open")
    for category_id in (groceries, shopping):
        await client.put(
            f"/envelopes/2026/8/allocations/{category_id}",
            json={"assigned_amount": "50.00"},
        )
    created = await client.post(
        "/transactions",
        json=txn_payload(account_id, category_id=groceries, amount="20.00", date="2026-08-10"),
    )
    assert created.status_code == 201, created.text
    moved = await client.patch(
        f"/transactions/{created.json()['id']}",
        json={"category_id": shopping},
    )
    assert moved.status_code == 200, moved.text
    rows = {
        row["category_id"]: row
        for row in (await client.get("/envelopes/2026/8")).json()["items"]
    }
    assert money(rows[groceries]["activity"]) == Decimal("0.00")
    assert money(rows[shopping]["activity"]) == Decimal("-20.00")


@pytest.mark.parametrize(
    "spend,flags",
    [
        ("40.00", {"rollover_positive": False}),
        ("140.00", {"rollover_negative": False}),
    ],
)
async def test_rollover_policy_can_drop_positive_or_negative_balance(
    client: AsyncClient,
    account_id: int,
    categories: dict[str, dict],
    spend: str,
    flags: dict,
):
    groceries = categories["Groceries"]["id"]
    await _income(client, account_id, categories["Salary"]["id"], "100.00", "2026-01-01")
    await client.post("/envelopes/2026/1/open")
    await client.put(
        f"/envelopes/2026/1/allocations/{groceries}",
        json={"assigned_amount": "100.00", **flags},
    )
    await client.post(
        "/transactions",
        json=txn_payload(account_id, category_id=groceries, amount=spend, date="2026-01-10"),
    )
    february = (await client.get("/envelopes/2026/2")).json()
    rows = [row for row in february["items"] if row["category_id"] == groceries]
    assert rows == []
