"""Envelope-month and allocation isolation using the server-authorized workspace."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from tests.test_core_workspace_isolation import (
    _bootstrap_user, _create_core_records, _login, _write_headers,
    workspace_auth_settings, workspace_client,
)


async def _two_scopes(client, maker):
    user, personal = await _bootstrap_user(maker, "envelope-owner@example.com")
    household = uuid4()
    async with maker() as session:
        await session.execute(text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:w, 'household', 'Envelope household', :u)"), {"w": household, "u": user})
        await session.execute(text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :w, :u, 'owner')"), {"id": uuid4(), "w": household, "u": user})
        await session.commit()
    csrf = await _login(client, "envelope-owner@example.com")
    first = await _create_core_records(client, csrf, personal, "personal")
    second = await _create_core_records(client, csrf, household, "household")
    return csrf, personal, household, first, second


async def test_envelope_reads_and_mutations_are_workspace_scoped(workspace_client, test_sessionmaker):
    client = workspace_client
    csrf, personal, household, first, second = await _two_scopes(client, test_sessionmaker)
    ph, hh = _write_headers(csrf, personal), _write_headers(csrf, household)

    # Personal owns 2026/8, household owns a separate 2026/9.
    assert (await client.post("/envelopes/2026/8/open", headers=ph)).status_code == 200
    personal_alloc = await client.put(
        "/envelopes/2026/8/allocations/{}".format(first["category"]["id"]),
        json={"assigned_amount": "0.00", "planned_amount": "10.00"},
        headers=ph,
    )
    assert personal_alloc.status_code == 200, personal_alloc.text
    assert (await client.post("/envelopes/2026/9/open", headers=hh)).status_code == 200
    household_alloc = await client.put(
        "/envelopes/2026/9/allocations/{}".format(second["category"]["id"]),
        json={"assigned_amount": "0.00", "planned_amount": "10.00"},
        headers=hh,
    )
    assert household_alloc.status_code == 200, household_alloc.text

    # Each workspace only lists its own months.
    assert (await client.get("/envelopes", headers=ph)).json() == [
        {"year": 2026, "month": 8, "is_closed": False, "has_ledger_drift": False}
    ]
    assert (await client.get("/envelopes", headers=hh)).json() == [
        {"year": 2026, "month": 9, "is_closed": False, "has_ledger_drift": False}
    ]

    # A foreign month/audit read does not disclose the other workspace's rows:
    # household closes its month, but personal still sees it as open and empty.
    assert (await client.get("/envelopes/2026/9/audit", headers=ph)).json() == []
    assert (await client.post("/envelopes/2026/9/close", headers=hh)).status_code == 200
    foreign_read = (await client.get("/envelopes/2026/9", headers=ph)).json()
    assert foreign_read["items"] == []
    assert foreign_read["is_closed"] is False
    assert (await client.get("/envelopes/2026/9", headers=hh)).json()["is_closed"] is True

    # Every mutation against a foreign month is a 404, never a write. (A PUT
    # naming a foreign category is rejected earlier by the category guard.)
    foreign = [
        await client.delete("/envelopes/2026/9/allocations/{}".format(second["category"]["id"]), headers=ph),
        await client.post("/envelopes/2026/9/moves", json={"from_category_id": second["category"]["id"], "to_category_id": second["category"]["id"], "amount": "1.00"}, headers=ph),
        await client.post("/envelopes/2026/9/fund", json={}, headers=ph),
        await client.post("/envelopes/2026/9/fund-next-month", headers=ph),
        await client.post("/envelopes/2026/9/close", headers=ph),
        await client.post("/envelopes/2026/9/reopen", headers=ph),
    ]
    for response in foreign:
        assert response.status_code == 404, "foreign month mutation must not be visible"
    # Writing a foreign category under a foreign month cannot succeed either.
    rejected = await client.put(
        "/envelopes/2026/9/allocations/{}".format(second["category"]["id"]),
        json={"assigned_amount": "5.00"},
        headers=ph,
    )
    assert rejected.status_code == 400

    # The owner's own month survives untouched.
    assert (await client.get("/envelopes", headers=hh)).json() == [
        {"year": 2026, "month": 9, "is_closed": True, "has_ledger_drift": False}
    ]


async def test_legacy_null_envelopes_hidden_from_authenticated_but_visible_when_auth_disabled(
    client, workspace_client, test_sessionmaker
):
    _, personal = await _bootstrap_user(test_sessionmaker, "envelope-legacy@example.com")
    csrf = await _login(workspace_client, "envelope-legacy@example.com")
    ph = _write_headers(csrf, personal)

    async with test_sessionmaker() as session:
        legacy_category = (
            await session.execute(text("SELECT id FROM categories WHERE workspace_id IS NULL LIMIT 1"))
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO envelope_months (workspace_id, year, month, is_closed) "
                "VALUES (NULL, 2030, 1, false)"
            )
        )
        await session.execute(
            text(
                "INSERT INTO envelope_allocations (workspace_id, year, month, category_id, assigned_amount, planned_amount) "
                "VALUES (NULL, 2030, 1, :c, 0, 0)"
            ),
            {"c": legacy_category},
        )
        await session.commit()

    # Authenticated workspace cannot see the NULL (legacy auth-disabled) namespace.
    assert (await workspace_client.get("/envelopes", headers=ph)).json() == []
    legacy_status = (await workspace_client.get("/envelopes/2030/1", headers=ph)).json()
    assert legacy_status["tracking_start"] is None
    assert legacy_status["items"] == []
    assert (
        await workspace_client.delete(
            "/envelopes/2030/1/allocations/{}".format(legacy_category), headers=ph
        )
    ).status_code == 404

    # Auth-disabled installation still sees every row, scoped or not.
    months = (await client.get("/envelopes")).json()
    assert {"year": 2030, "month": 1, "is_closed": False, "has_ledger_drift": False} in months
    visible = (await client.get("/envelopes/2030/1")).json()
    assert visible["tracking_start"] == {"year": 2030, "month": 1}
    row = next(item for item in visible["items"] if item["category_id"] == legacy_category)
    assert row["has_row"] is True
    assert Decimal(str(row["assigned_amount"])) == Decimal("0.00")