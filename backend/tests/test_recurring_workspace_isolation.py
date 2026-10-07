"""Recurring-transaction isolation using the server-authorized workspace.

Mirrors tests/test_budget_workspace_isolation.py: an authenticated caller may
only list, read, update, delete or post its own workspace's recurring
templates, a NULL-scoped legacy template stays invisible to it, and the
auth-disabled path keeps its original installation-wide view.
"""
from uuid import uuid4

from sqlalchemy import text

from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _create_core_records,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


async def _two_scopes(client, maker):
    user, personal = await _bootstrap_user(maker, "recurring-owner@example.com")
    household = uuid4()
    async with maker() as session:
        await session.execute(
            text(
                "INSERT INTO workspaces (id, kind, display_name, created_by_user_id) "
                "VALUES (:w, 'household', 'Recurring household', :u)"
            ),
            {"w": household, "u": user},
        )
        await session.execute(
            text(
                "INSERT INTO workspace_memberships (id, workspace_id, user_id, role) "
                "VALUES (:id, :w, :u, 'owner')"
            ),
            {"id": uuid4(), "w": household, "u": user},
        )
        await session.commit()
    csrf = await _login(client, "recurring-owner@example.com")
    first = await _create_core_records(client, csrf, personal, "personal")
    second = await _create_core_records(client, csrf, household, "household")
    return csrf, personal, household, first, second


def _recurring_payload(account_id: int, category_id: int, description: str = "Rent") -> dict:
    return {
        "account_id": account_id,
        "category_id": category_id,
        "type": "expense",
        "amount": "10.00",
        "description": description,
        "frequency": "monthly",
        "anchor_date": "2026-01-15",
    }


async def test_recurring_lists_and_mutations_are_workspace_scoped(
    workspace_client, test_sessionmaker
):
    client = workspace_client
    csrf, personal, household, first, second = await _two_scopes(client, test_sessionmaker)
    personal_headers = _write_headers(csrf, personal)
    household_headers = _write_headers(csrf, household)

    created = await client.post(
        "/recurring",
        json=_recurring_payload(first["account"]["id"], first["category"]["id"]),
        headers=personal_headers,
    )
    assert created.status_code == 201, created.text
    recurring_id = created.json()["id"]

    # A different workspace cannot list it...
    assert (await client.get("/recurring", headers=household_headers)).json() == []
    # ...nor update, delete or post it, and the id is never confirmed to exist.
    for method, path in (
        ("patch", f"/recurring/{recurring_id}"),
        ("delete", f"/recurring/{recurring_id}"),
        ("post", f"/recurring/{recurring_id}/post"),
    ):
        kwargs = {"json": {"amount": "20.00"}} if method == "patch" else {}
        response = await getattr(client, method)(path, headers=household_headers, **kwargs)
        assert response.status_code == 404, (method, response.text)

    # The owning workspace still sees and can act on its own template.
    own = (await client.get("/recurring", headers=personal_headers)).json()
    assert [row["id"] for row in own] == [recurring_id]
    patched = await client.patch(
        f"/recurring/{recurring_id}", json={"amount": "20.00"}, headers=personal_headers
    )
    assert patched.status_code == 200, patched.text
    posted = await client.post(f"/recurring/{recurring_id}/post", headers=personal_headers)
    assert posted.status_code == 201, posted.text

    # Posting minted a Transaction inside the caller's own workspace.
    async with test_sessionmaker() as session:
        scopes = (
            await session.execute(
                text("SELECT workspace_id FROM transactions WHERE description = 'Rent'")
            )
        ).scalars().all()
    assert scopes and all(str(scope) == str(personal) for scope in scopes)


async def test_legacy_null_scoped_recurring_is_invisible_to_authenticated_workspace(
    workspace_client, test_sessionmaker
):
    client = workspace_client
    csrf, personal, household, first, second = await _two_scopes(client, test_sessionmaker)
    headers = _write_headers(csrf, personal)

    created = await client.post(
        "/recurring",
        json=_recurring_payload(first["account"]["id"], first["category"]["id"], "Scoped template"),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    # A legacy (auth-disabled namespace) template referencing the seeded
    # NULL-scoped account/category must never surface to an authenticated
    # caller — not even by id.
    async with test_sessionmaker() as session:
        account_id = (
            await session.execute(text("SELECT id FROM accounts WHERE workspace_id IS NULL LIMIT 1"))
        ).scalar_one()
        category_id = (
            await session.execute(text("SELECT id FROM categories WHERE workspace_id IS NULL LIMIT 1"))
        ).scalar_one()
        legacy_id = (
            await session.execute(
                text(
                    "INSERT INTO recurring_transactions "
                    "(workspace_id, account_id, category_id, type, amount, description, frequency, anchor_date, is_active) "
                    "VALUES (NULL, :a, :c, 'EXPENSE', 10, 'Legacy template', 'MONTHLY', '2026-01-15', true) "
                    "RETURNING id"
                ),
                {"a": account_id, "c": category_id},
            )
        ).scalar_one()
        await session.commit()

    listed = (await client.get("/recurring", headers=headers)).json()
    assert [row["id"] for row in listed] == [created.json()["id"]]

    for method, path in (
        ("patch", f"/recurring/{legacy_id}"),
        ("delete", f"/recurring/{legacy_id}"),
        ("post", f"/recurring/{legacy_id}/post"),
    ):
        kwargs = {"json": {"amount": "20.00"}} if method == "patch" else {}
        response = await getattr(client, method)(path, headers=headers, **kwargs)
        assert response.status_code == 404, (method, response.text)


async def test_auth_disabled_recurring_still_sees_every_template(
    client, test_sessionmaker, account_id, categories
):
    payload = _recurring_payload(account_id, categories["Groceries"]["id"])
    first = await client.post("/recurring", json={**payload, "description": "Legacy one"})
    second = await client.post("/recurring", json={**payload, "description": "Legacy two"})
    assert (first.status_code, second.status_code) == (201, 201), (first.text, second.text)

    # A directly-inserted NULL-scoped row is part of the same namespace.
    async with test_sessionmaker() as session:
        raw_id = (
            await session.execute(
                text(
                    "INSERT INTO recurring_transactions "
                    "(workspace_id, account_id, category_id, type, amount, description, frequency, anchor_date, is_active) "
                    "VALUES (NULL, :a, :c, 'EXPENSE', 10, 'Legacy raw', 'MONTHLY', '2026-01-15', true) "
                    "RETURNING id"
                ),
                {"a": account_id, "c": categories["Groceries"]["id"]},
            )
        ).scalar_one()
        await session.commit()

    listed = (await client.get("/recurring")).json()
    assert {row["id"] for row in listed} == {first.json()["id"], second.json()["id"], raw_id}