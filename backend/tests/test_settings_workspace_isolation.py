"""Workspace-scoped AppSettings API and bootstrap contracts."""
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.settings import AppSettings
from app.models.workspace import WorkspaceMembership, WorkspaceRole
from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


async def test_authenticated_workspaces_read_and_update_only_their_own_settings(workspace_client, test_sessionmaker):
    user_id, first_workspace = await _bootstrap_user(test_sessionmaker, "settings-owner@example.com")
    second_workspace = uuid4()
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO workspaces (id, kind, display_name, created_by_user_id) "
                "VALUES (:id, 'household', 'Second', :user)"
            ),
            {"id": second_workspace, "user": user_id},
        )
        await session.execute(
            text(
                "INSERT INTO workspace_memberships (id, workspace_id, user_id, role) "
                "VALUES (:id, :workspace, :user, 'owner')"
            ),
            {"id": uuid4(), "workspace": second_workspace, "user": user_id},
        )
        await session.commit()

    csrf = await _login(workspace_client, "settings-owner@example.com")
    first_headers = _write_headers(csrf, first_workspace)
    second_headers = _write_headers(csrf, second_workspace)

    first = await workspace_client.patch(
        "/settings",
        json={"currency": "EUR", "idle_cash_threshold_days": 12},
        headers=first_headers,
    )
    second = await workspace_client.patch(
        "/settings",
        json={"currency": "GBP", "idle_cash_threshold_days": 99},
        headers=second_headers,
    )
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["currency"] == "EUR"
    assert second.json()["currency"] == "GBP"

    first_read = await workspace_client.get("/settings", headers={"X-Aurum-Workspace": str(first_workspace)})
    second_read = await workspace_client.get("/settings", headers={"X-Aurum-Workspace": str(second_workspace)})
    assert first_read.json()["currency"] == "EUR"
    assert first_read.json()["idle_cash_threshold_days"] == 12
    assert second_read.json()["currency"] == "GBP"
    assert second_read.json()["idle_cash_threshold_days"] == 99


async def test_authenticated_settings_hide_legacy_row_and_viewer_cannot_patch(workspace_client, test_sessionmaker):
    owner_id, _ = await _bootstrap_user(test_sessionmaker, "settings-viewer@example.com")
    viewer_id, _ = await _bootstrap_user(test_sessionmaker, "settings-reader@example.com")
    workspace_id = uuid4()
    async with test_sessionmaker() as session:
        legacy = await session.get(AppSettings, 1)
        legacy.currency = "JPY"
        await session.execute(
            text(
                "INSERT INTO workspaces (id, kind, display_name, created_by_user_id) "
                "VALUES (:id, 'household', 'Shared settings', :user)"
            ),
            {"id": workspace_id, "user": owner_id},
        )
        session.add(
            WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=owner_id,
                role=WorkspaceRole.OWNER,
            )
        )
        session.add(
            WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=viewer_id,
                role=WorkspaceRole.VIEWER,
            )
        )
        await session.commit()

    owner_csrf = await _login(workspace_client, "settings-viewer@example.com")
    owner = await workspace_client.get("/settings", headers={"X-Aurum-Workspace": str(workspace_id)})
    assert owner.status_code == 200
    assert owner.json()["currency"] != "JPY"

    viewer_csrf = await _login(workspace_client, "settings-reader@example.com")
    viewer = await workspace_client.patch(
        "/settings",
        json={"currency": "CAD"},
        headers=_write_headers(viewer_csrf, workspace_id),
    )
    assert viewer.status_code == 403


async def test_workspace_bootstraps_stage_one_settings_row_and_scope_is_immutable(test_sessionmaker):
    from app.services.workspace_service import create_household

    async with test_sessionmaker() as session:
        # This test only exercises the household factory because the first-owner
        # capability validation is covered elsewhere.
        user_id, personal_workspace_id = await _bootstrap_user(test_sessionmaker, "settings-bootstrap@example.com")
        household, _ = await create_household(
            session,
            creator_id=user_id,
            display_name="Settings household",
            default_currency="CHF",
        )
        await session.commit()
        rows = (
            await session.execute(
                select(AppSettings).where(AppSettings.workspace_id.in_([personal_workspace_id, household.id]))
            )
        ).scalars().all()
        assert [(row.workspace_id, row.currency) for row in rows] == [(household.id, "CHF")]

        try:
            await session.execute(
                text("UPDATE app_settings SET workspace_id = :id WHERE id = :settings_id"),
                {"id": personal_workspace_id, "settings_id": rows[0].id},
            )
        except DBAPIError as exc:
            assert "settings workspace is immutable" in str(exc)
        else:
            raise AssertionError("workspace ownership must be immutable")


async def test_database_allows_only_one_scoped_settings_row_per_workspace(test_sessionmaker):
    from app.services.workspace_service import create_household

    user_id, _ = await _bootstrap_user(test_sessionmaker, "settings-unique@example.com")
    async with test_sessionmaker() as session:
        workspace, _ = await create_household(
            session,
            creator_id=user_id,
            display_name="Unique settings household",
        )
        await session.commit()

    async with test_sessionmaker() as session:
        session.add(AppSettings(workspace_id=workspace.id, currency="EUR"))
        with pytest.raises(IntegrityError, match="uq_app_settings_workspace_id"):
            await session.commit()
