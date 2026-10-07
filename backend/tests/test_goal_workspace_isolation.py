"""Savings-goal isolation using the server-authorized workspace.

Goal is a workspace-owned root; GoalContribution has no workspace_id of its
own, so a contribution is only ever reachable through its parent goal — which
is why a foreign goal id must 404 the contribution route without writing a row.
"""
from uuid import uuid4

from sqlalchemy import text

from tests.helpers import money
from tests.test_core_workspace_isolation import (
    _bootstrap_user, _login, _write_headers, workspace_auth_settings, workspace_client,
)


async def _two_scopes(client, maker):
    user, personal = await _bootstrap_user(maker, "goal-owner@example.com")
    household = uuid4()
    async with maker() as session:
        await session.execute(
            text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:w, 'household', 'Goal household', :u)"),
            {"w": household, "u": user},
        )
        await session.execute(
            text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :w, :u, 'owner')"),
            {"id": uuid4(), "w": household, "u": user},
        )
        await session.commit()
    csrf = await _login(client, "goal-owner@example.com")
    return csrf, personal, household


async def _create_goal(client, headers, name: str) -> int:
    response = await client.post("/goals", json={"name": name, "target_amount": "1000"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_goal_reads_and_mutations_are_scoped(workspace_client, test_sessionmaker):
    client = workspace_client
    csrf, personal, household = await _two_scopes(client, test_sessionmaker)
    ph, hh = _write_headers(csrf, personal), _write_headers(csrf, household)
    personal_goal = await _create_goal(client, ph, "Personal goal")
    household_goal = await _create_goal(client, hh, "Household goal")

    assert [g["id"] for g in (await client.get("/goals", headers=ph)).json()] == [personal_goal]
    assert [g["id"] for g in (await client.get("/goals", headers=hh)).json()] == [household_goal]

    # Workspace A cannot read, update, delete or contribute to B's goal.
    assert (await client.patch(f"/goals/{household_goal}", json={"target_amount": "2000"}, headers=ph)).status_code == 404
    assert (await client.delete(f"/goals/{household_goal}", headers=ph)).status_code == 404
    contribution = await client.post(
        f"/goals/{household_goal}/contributions", json={"amount": "100", "date": "2026-01-15"}, headers=ph
    )
    assert contribution.status_code == 404

    # The foreign goal is untouched: still present, still zero, no leaked row.
    household_rows = (await client.get("/goals", headers=hh)).json()
    assert [g["id"] for g in household_rows] == [household_goal]
    assert money(household_rows[0]["current_amount"]) == money(0)

    # A caller still mutates and contributes to its own goal.
    assert (await client.patch(f"/goals/{personal_goal}", json={"target_amount": "2000"}, headers=ph)).status_code == 200
    assert (
        await client.post(f"/goals/{personal_goal}/contributions", json={"amount": "100", "date": "2026-01-15"}, headers=ph)
    ).status_code == 201
    assert (await client.delete(f"/goals/{personal_goal}", headers=ph)).status_code == 204
    assert (await client.get("/goals", headers=ph)).json() == []


async def test_legacy_null_goal_is_invisible_to_authenticated_caller(workspace_client, test_sessionmaker):
    client = workspace_client
    _, personal = await _bootstrap_user(test_sessionmaker, "legacy-reader@example.com")
    csrf = await _login(client, "legacy-reader@example.com")
    headers = _write_headers(csrf, personal)
    async with test_sessionmaker() as session:
        legacy_id = (
            await session.execute(
                text("INSERT INTO goals (workspace_id, name, target_amount) VALUES (NULL, 'Legacy goal', 1000) RETURNING id")
            )
        ).scalar_one()
        await session.commit()

    assert (await client.get("/goals", headers=headers)).json() == []
    assert (await client.patch(f"/goals/{legacy_id}", json={"target_amount": "2000"}, headers=headers)).status_code == 404
    assert (await client.delete(f"/goals/{legacy_id}", headers=headers)).status_code == 404
    assert (
        await client.post(f"/goals/{legacy_id}/contributions", json={"amount": "100", "date": "2026-01-15"}, headers=headers)
    ).status_code == 404
    async with test_sessionmaker() as session:
        assert (await session.execute(text("SELECT id FROM goals WHERE id=:id"), {"id": legacy_id})).scalar_one() == legacy_id


async def test_auth_disabled_path_sees_scoped_and_legacy_goals(client, test_sessionmaker):
    _, workspace_id = await _bootstrap_user(test_sessionmaker, "legacy-viewer@example.com")
    async with test_sessionmaker() as session:
        scoped_id = (
            await session.execute(
                text("INSERT INTO goals (workspace_id, name, target_amount) VALUES (:w, 'Scoped goal', 1000) RETURNING id"),
                {"w": workspace_id},
            )
        ).scalar_one()
        await session.commit()
    legacy = (await client.post("/goals", json={"name": "Legacy goal", "target_amount": "500"})).json()

    ids = {g["id"] for g in (await client.get("/goals")).json()}
    assert scoped_id in ids
    assert legacy["id"] in ids