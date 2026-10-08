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


async def test_envelope_audits_and_templates_are_workspace_scoped(
    client, workspace_client, test_sessionmaker
):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    personal_headers = _write_headers(csrf, personal)
    household_headers = _write_headers(csrf, household)
    personal_category = first["category"]["id"]
    household_category = second["category"]["id"]

    # Use the same calendar month in both workspaces. The audit list must not
    # merge rows merely because year/month match.
    for headers, category_id in ((personal_headers, personal_category), (household_headers, household_category)):
        opened = await workspace_client.post("/envelopes/2027/4/open", headers=headers)
        assert opened.status_code == 200, opened.text
        allocated = await workspace_client.put(
            f"/envelopes/2027/4/allocations/{category_id}",
            json={"assigned_amount": "0.00", "planned_amount": "10.00"},
            headers=headers,
        )
        assert allocated.status_code == 200, allocated.text

    personal_audit = (await workspace_client.get("/envelopes/2027/4/audit", headers=personal_headers)).json()
    household_audit = (await workspace_client.get("/envelopes/2027/4/audit", headers=household_headers)).json()
    assert [row["category_id"] for row in personal_audit] == [personal_category]
    assert [row["category_id"] for row in household_audit] == [household_category]

    personal_template = await workspace_client.post(
        "/envelopes/templates",
        json={"name": "Monthly plan", "items": [{"category_id": personal_category, "planned_amount": "10.00"}]},
        headers=personal_headers,
    )
    household_template = await workspace_client.post(
        "/envelopes/templates",
        json={"name": "Monthly plan", "items": [{"category_id": household_category, "planned_amount": "10.00"}]},
        headers=household_headers,
    )
    assert personal_template.status_code == 201, personal_template.text
    assert household_template.status_code == 201, household_template.text
    personal_template_id = personal_template.json()["id"]
    household_template_id = household_template.json()["id"]

    assert [row["id"] for row in (await workspace_client.get("/envelopes/templates", headers=personal_headers)).json()] == [
        personal_template_id
    ]
    assert [row["id"] for row in (await workspace_client.get("/envelopes/templates", headers=household_headers)).json()] == [
        household_template_id
    ]

    foreign_payload = {"name": "tamper", "items": [{"category_id": personal_category, "planned_amount": "1.00"}]}
    assert (
        await workspace_client.patch(
            f"/envelopes/templates/{household_template_id}", json=foreign_payload, headers=personal_headers
        )
    ).status_code == 404
    assert (
        await workspace_client.delete(f"/envelopes/templates/{household_template_id}", headers=personal_headers)
    ).status_code == 404
    assert (
        await workspace_client.post(
            f"/envelopes/2027/4/apply-template/{household_template_id}", headers=personal_headers
        )
    ).status_code == 404

    # Compatibility mode remains installation-wide, including both scoped rows.
    assert {row["id"] for row in (await client.get("/envelopes/templates")).json()} >= {
        personal_template_id,
        household_template_id,
    }


async def test_legacy_null_template_is_hidden_from_authenticated_workspace(
    client, workspace_client, test_sessionmaker
):
    _, personal = await _bootstrap_user(test_sessionmaker, "envelope-template-legacy@example.com")
    csrf = await _login(workspace_client, "envelope-template-legacy@example.com")
    headers = _write_headers(csrf, personal)

    async with test_sessionmaker() as session:
        category_id = (
            await session.execute(text("SELECT id FROM categories WHERE workspace_id IS NULL LIMIT 1"))
        ).scalar_one()
        template_id = (
            await session.execute(
                text("INSERT INTO envelope_templates (workspace_id, name) VALUES (NULL, 'Legacy plan') RETURNING id")
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO envelope_template_items (template_id, category_id, planned_amount) "
                "VALUES (:template_id, :category_id, 1)"
            ),
            {"template_id": template_id, "category_id": category_id},
        )
        await session.commit()

    assert (await workspace_client.get("/envelopes/templates", headers=headers)).json() == []
    assert (
        await workspace_client.delete(f"/envelopes/templates/{template_id}", headers=headers)
    ).status_code == 404
    assert template_id in {row["id"] for row in (await client.get("/envelopes/templates")).json()}