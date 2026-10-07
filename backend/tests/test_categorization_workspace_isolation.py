"""Workspace isolation for categorization rules.

An authenticated caller may only list, read, match against, update or delete
their own workspace's rules; a rule owned by another workspace (or a legacy
NULL-scoped rule from the auth-disabled namespace) must never affect them.
The auth-disabled installation keeps seeing every rule, unchanged.
"""
from sqlalchemy import text

from tests.test_core_workspace_isolation import (  # noqa: F401
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


async def _create_category(client, csrf, workspace_id, *, name: str) -> int:
    response = await client.post(
        "/categories",
        json={"name": name, "kind": "expense", "color": "#2a78d6"},
        headers=_write_headers(csrf, workspace_id),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_rule(client, csrf, workspace_id, *, category_id: int, pattern: str, name: str) -> dict:
    response = await client.post(
        "/categorization-rules",
        json={"name": name, "pattern": pattern, "category_id": category_id},
        headers=_write_headers(csrf, workspace_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _match(client, csrf, workspace_id, *, description: str, account_id: int) -> dict:
    response = await client.post(
        "/categorization-rules/match",
        json={
            "description": description,
            "amount": "10.00",
            "currency": "KZT",
            "account_id": account_id,
            "transaction_type": "expense",
        },
        headers=_write_headers(csrf, workspace_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_account(client, csrf, workspace_id, *, name: str) -> int:
    response = await client.post(
        "/accounts",
        json={"name": name, "type": "cash", "currency": "KZT"},
        headers=_write_headers(csrf, workspace_id),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _insert_null_workspace_rule(test_sessionmaker, *, category_id: int, pattern: str, name: str) -> int:
    """The legacy auth-disabled namespace: a rule with no workspace at all."""
    async with test_sessionmaker() as session:
        rule_id = (
            await session.execute(
                text(
                    """
                    INSERT INTO categorization_rules
                        (priority, is_enabled, name, match_type, pattern, category_id, workspace_id)
                    VALUES (0, true, :name, 'CONTAINS', :pattern, :category_id, NULL)
                    RETURNING id
                    """
                ),
                {"name": name, "pattern": pattern, "category_id": category_id},
            )
        ).scalar_one()
        await session.commit()
    return rule_id


async def test_foreign_rule_is_invisible_and_not_mutable(workspace_client, test_sessionmaker):
    _, workspace_a = await _bootstrap_user(test_sessionmaker, "rules-a@example.com")
    _, workspace_b = await _bootstrap_user(test_sessionmaker, "rules-b@example.com")

    csrf_a = await _login(workspace_client, "rules-a@example.com")
    category_a = await _create_category(workspace_client, csrf_a, workspace_a, name="Rules A")
    rule_a = await _create_rule(
        workspace_client, csrf_a, workspace_a, category_id=category_a, pattern="alpha", name="A rule"
    )

    workspace_client.cookies.clear()
    csrf_b = await _login(workspace_client, "rules-b@example.com")
    category_b = await _create_category(workspace_client, csrf_b, workspace_b, name="Rules B")
    rule_b = await _create_rule(
        workspace_client, csrf_b, workspace_b, category_id=category_b, pattern="beta", name="B rule"
    )

    # Back to A.
    workspace_client.cookies.clear()
    csrf_a = await _login(workspace_client, "rules-a@example.com")

    listed = (
        await workspace_client.get(
            "/categorization-rules", headers={"X-Aurum-Workspace": str(workspace_a)}
        )
    ).json()
    assert [rule["id"] for rule in listed] == [rule_a["id"]]

    # get-by-id / update / delete of a foreign rule all read as 404 — no
    # disclosure that the id even exists.
    patch = await workspace_client.patch(
        f"/categorization-rules/{rule_b['id']}",
        json={"name": "probe"},
        headers=_write_headers(csrf_a, workspace_a),
    )
    assert patch.status_code == 404
    delete = await workspace_client.delete(
        f"/categorization-rules/{rule_b['id']}",
        headers=_write_headers(csrf_a, workspace_a),
    )
    assert delete.status_code == 404


async def test_foreign_rules_never_influence_categorization(workspace_client, test_sessionmaker):
    _, workspace_a = await _bootstrap_user(test_sessionmaker, "cat-a@example.com")
    _, workspace_b = await _bootstrap_user(test_sessionmaker, "cat-b@example.com")

    csrf_a = await _login(workspace_client, "cat-a@example.com")
    category_a = await _create_category(workspace_client, csrf_a, workspace_a, name="Cat A")
    account_a = await _create_account(workspace_client, csrf_a, workspace_a, name="Account A")
    await _create_rule(
        workspace_client, csrf_a, workspace_a, category_id=category_a, pattern="alpha", name="A rule"
    )

    workspace_client.cookies.clear()
    csrf_b = await _login(workspace_client, "cat-b@example.com")
    category_b = await _create_category(workspace_client, csrf_b, workspace_b, name="Cat B")
    await _create_rule(
        workspace_client, csrf_b, workspace_b, category_id=category_b, pattern="beta", name="B rule"
    )

    workspace_client.cookies.clear()
    csrf_a = await _login(workspace_client, "cat-a@example.com")

    # B's rule would match "beta purchase", but is invisible to A.
    foreign = await _match(
        workspace_client, csrf_a, workspace_a, description="beta purchase", account_id=account_a
    )
    assert foreign["rule_id"] is None

    # A's own rule still applies to A.
    own = await _match(
        workspace_client, csrf_a, workspace_a, description="alpha purchase", account_id=account_a
    )
    assert own["rule_id"] is not None
    assert own["category_id"] == category_a

    # The create path agrees: B's rule cannot fill a category on an A transaction.
    created = await workspace_client.post(
        "/transactions",
        json={
            "account_id": account_a,
            "type": "expense",
            "amount": "10.00",
            "currency": "KZT",
            "description": "beta purchase",
            "date": "2026-01-15",
        },
        headers=_write_headers(csrf_a, workspace_a),
    )
    assert created.status_code == 201, created.text
    assert created.json()["category_id"] is None


async def test_null_scoped_legacy_rule_is_not_applied_to_authenticated_caller(
    workspace_client, test_sessionmaker, client, categories
):
    legacy_category = categories["Groceries"]["id"]
    await _insert_null_workspace_rule(
        test_sessionmaker, category_id=legacy_category, pattern="legacy", name="Legacy"
    )

    _, workspace_a = await _bootstrap_user(test_sessionmaker, "null-a@example.com")
    csrf_a = await _login(workspace_client, "null-a@example.com")
    account_a = await _create_account(workspace_client, csrf_a, workspace_a, name="Account A")

    listed = (
        await workspace_client.get(
            "/categorization-rules", headers={"X-Aurum-Workspace": str(workspace_a)}
        )
    ).json()
    assert listed == []

    matched = await _match(
        workspace_client, csrf_a, workspace_a, description="legacy merchant", account_id=account_a
    )
    assert matched["rule_id"] is None
    assert matched["category_id"] is None


async def test_auth_disabled_sees_every_workspace_rule(workspace_client, test_sessionmaker, client, categories):
    _, workspace_a = await _bootstrap_user(test_sessionmaker, "all-a@example.com")
    _, workspace_b = await _bootstrap_user(test_sessionmaker, "all-b@example.com")

    csrf_a = await _login(workspace_client, "all-a@example.com")
    category_a = await _create_category(workspace_client, csrf_a, workspace_a, name="All A")
    rule_a = await _create_rule(
        workspace_client, csrf_a, workspace_a, category_id=category_a, pattern="alpha", name="A rule"
    )

    workspace_client.cookies.clear()
    csrf_b = await _login(workspace_client, "all-b@example.com")
    category_b = await _create_category(workspace_client, csrf_b, workspace_b, name="All B")
    rule_b = await _create_rule(
        workspace_client, csrf_b, workspace_b, category_id=category_b, pattern="beta", name="B rule"
    )

    legacy_rule = await _insert_null_workspace_rule(
        test_sessionmaker, category_id=categories["Groceries"]["id"], pattern="legacy", name="Legacy"
    )

    # The auth-disabled installation is the NULL workspace and keeps seeing
    # everything, exactly as it did before scoping existed.
    visible = {rule["id"] for rule in (await client.get("/categorization-rules")).json()}
    assert {rule_a["id"], rule_b["id"], legacy_rule} <= visible