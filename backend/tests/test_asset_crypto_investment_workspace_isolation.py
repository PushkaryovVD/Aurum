"""Workspace isolation for the assets / crypto / investments families.

Reuses the authenticated-app fixtures and bootstrap helpers from the core
isolation test (same shared test cluster), and drives the real HTTP routes.
It proves three things for every root model in scope:

* a caller authorized for workspace A cannot read, update or delete a row
  owned by workspace B (404, never a disclosure of existence),
* a legacy ``workspace_id IS NULL`` row is invisible to any authenticated
  caller, and
* the auth-disabled path (``context.workspace_id is None``) still sees every
  row exactly as it did before scoping existed.

``asset_service.py`` does not exist in this codebase — the asset routes hold
their own logic — so the asset family is exercised through the routes.
"""
from uuid import uuid4

from sqlalchemy import text

from tests.test_core_workspace_isolation import (
    _bootstrap_user,
    _login,
    _write_headers,
    workspace_auth_settings,
    workspace_client,
)


def _asset_payload(name: str) -> dict:
    return {
        "name": name,
        "asset_class": "other",
        "currency": "KZT",
        "value": "100.00",
        "as_of_date": "2026-01-15",
        "exchange_rate_to_kzt": "1",
    }


async def _second_workspace(maker, user_id, display_name: str = "Second"):
    workspace_id = uuid4()
    async with maker() as session:
        await session.execute(
            text(
                "INSERT INTO workspaces (id, kind, display_name, created_by_user_id) "
                "VALUES (:workspace_id, 'household', :name, :user_id)"
            ),
            {"workspace_id": workspace_id, "name": display_name, "user_id": user_id},
        )
        await session.execute(
            text(
                "INSERT INTO workspace_memberships (id, workspace_id, user_id, role) "
                "VALUES (:id, :workspace_id, :user_id, 'owner')"
            ),
            {"id": uuid4(), "workspace_id": workspace_id, "user_id": user_id},
        )
        await session.commit()
    return workspace_id


async def _investment_portfolio(client, headers, name: str) -> dict:
    account = (
        await client.post(
            "/accounts", json={"name": f"Broker {name}", "type": "investment", "currency": "KZT"}, headers=headers
        )
    )
    assert account.status_code == 201, account.text
    portfolio = await client.post(
        "/investments/portfolios", json={"name": name, "account_id": account.json()["id"]}, headers=headers
    )
    assert portfolio.status_code == 201, portfolio.text
    return portfolio.json()


async def test_assets_crypto_and_investments_are_workspace_scoped(workspace_client, test_sessionmaker):
    user_id, workspace_a = await _bootstrap_user(test_sessionmaker, "owner@example.com")
    workspace_b = await _second_workspace(test_sessionmaker, user_id)
    csrf = await _login(workspace_client, "owner@example.com")
    headers_a, headers_b = _write_headers(csrf, workspace_a), _write_headers(csrf, workspace_b)

    asset_a = (await workspace_client.post("/assets", json=_asset_payload("Asset A"), headers=headers_a)).json()
    asset_b = (await workspace_client.post("/assets", json=_asset_payload("Asset B"), headers=headers_b)).json()
    crypto_a = (
        await workspace_client.post("/crypto/portfolios", json={"name": "Crypto A"}, headers=headers_a)
    ).json()
    crypto_b = (
        await workspace_client.post("/crypto/portfolios", json={"name": "Crypto B"}, headers=headers_b)
    ).json()
    investment_a = await _investment_portfolio(workspace_client, headers_a, "Port A")
    investment_b = await _investment_portfolio(workspace_client, headers_b, "Port B")

    read_a = {"X-Aurum-Workspace": str(workspace_a)}
    read_b = {"X-Aurum-Workspace": str(workspace_b)}

    # Reads are scoped: each workspace sees only its own roots.
    assert [row["id"] for row in (await workspace_client.get("/assets", headers=read_a)).json()] == [asset_a["id"]]
    assert [row["id"] for row in (await workspace_client.get("/assets", headers=read_b)).json()] == [asset_b["id"]]
    assert [row["id"] for row in (await workspace_client.get("/crypto/portfolios", headers=read_a)).json()] == [
        crypto_a["id"]
    ]
    assert [row["id"] for row in (await workspace_client.get("/investments/portfolios", headers=read_a)).json()] == [
        investment_a["id"]
    ]

    # get-by-id fetches run through the scope filter: a foreign id 404s and
    # leaks nothing about whether the row exists.
    assert (
        await workspace_client.get(f"/assets/{asset_b['id']}/valuations", headers=read_a)
    ).status_code == 404
    assert (
        await workspace_client.patch(f"/assets/{asset_b['id']}", json={"name": "probe"}, headers=headers_a)
    ).status_code == 404
    assert (await workspace_client.delete(f"/assets/{asset_b['id']}", headers=headers_a)).status_code == 404

    assert (
        await workspace_client.patch(
            f"/crypto/portfolios/{crypto_b['id']}", json={"name": "probe"}, headers=headers_a
        )
    ).status_code == 404
    assert (
        await workspace_client.delete(f"/crypto/portfolios/{crypto_b['id']}", headers=headers_a)
    ).status_code == 404

    # A security living in workspace B is unreachable from workspace A, and a
    # new security cannot be filed under B's portfolio nor under B's account.
    security_b = await workspace_client.post(
        "/investments/securities",
        json={"portfolio_id": investment_b["id"], "name": "Kazatomprom", "ticker": "KZAP", "currency": "KZT"},
        headers=headers_b,
    )
    assert security_b.status_code == 201, security_b.text
    security_b_id = security_b.json()["asset_id"]

    assert [
        row["asset_id"] for row in (await workspace_client.get("/investments/positions", headers=read_a)).json()
    ] == []
    probe_trade = await workspace_client.post(
        f"/investments/securities/{security_b_id}/trades",
        json={"type": "buy", "quantity": "1", "price_per_unit": "100", "fee": "0", "date": "2026-01-15"},
        headers=headers_a,
    )
    assert probe_trade.status_code == 404, probe_trade.text
    probe_price = await workspace_client.put(
        f"/investments/securities/{security_b_id}/price",
        json={"price_per_unit": "100", "as_of_date": "2026-01-15"},
        headers=headers_a,
    )
    assert probe_price.status_code == 404, probe_price.text
    foreign_security = await workspace_client.post(
        "/investments/securities",
        json={"portfolio_id": investment_b["id"], "name": "X", "ticker": "X", "currency": "KZT"},
        headers=headers_a,
    )
    assert foreign_security.status_code == 404, foreign_security.text

    # Filing a portfolio against workspace B's cash account is refused too.
    account_b = (await workspace_client.get("/accounts", headers=read_b)).json()[0]["id"]
    foreign_account = await workspace_client.post(
        "/investments/portfolios", json={"name": "Probe", "account_id": account_b}, headers=headers_a
    )
    assert foreign_account.status_code == 400, foreign_account.text


async def test_legacy_null_rows_hidden_from_authenticated_but_visible_to_auth_disabled(
    client, workspace_client, test_sessionmaker
):
    # Auth-disabled writes land in the legacy NULL namespace.
    legacy_asset = (await client.post("/assets", json=_asset_payload("Legacy asset"))).json()
    legacy_crypto = (await client.post("/crypto/portfolios", json={"name": "Legacy crypto"})).json()
    legacy_account = (
        await client.post("/accounts", json={"name": "Legacy broker", "type": "investment", "currency": "KZT"})
    ).json()
    legacy_investment = (
        await client.post(
            "/investments/portfolios", json={"name": "Legacy port", "account_id": legacy_account["id"]}
        )
    ).json()

    # A scoped row in workspace A, written through the authenticated app.
    user_id, workspace_a = await _bootstrap_user(test_sessionmaker, "owner2@example.com")
    workspace_b = await _second_workspace(test_sessionmaker, user_id, "Other")
    csrf = await _login(workspace_client, "owner2@example.com")
    scoped_asset = (
        await workspace_client.post(
            "/assets", json=_asset_payload("Scoped asset"), headers=_write_headers(csrf, workspace_a)
        )
    ).json()

    headers_a = {"X-Aurum-Workspace": str(workspace_a)}
    headers_b = {"X-Aurum-Workspace": str(workspace_b)}

    # Authenticated workspace A sees only its own row — the NULL legacy rows
    # are invisible.
    assert [row["id"] for row in (await workspace_client.get("/assets", headers=headers_a)).json()] == [
        scoped_asset["id"]
    ]
    assert (await workspace_client.get("/crypto/portfolios", headers=headers_a)).json() == []
    assert (await workspace_client.get("/investments/portfolios", headers=headers_a)).json() == []

    # A foreign workspace sees neither the scoped row nor the legacy rows.
    assert (await workspace_client.get("/assets", headers=headers_b)).json() == []

    # Mutating a legacy row through the authenticated app is a 404.
    assert (
        await workspace_client.patch(
            f"/assets/{legacy_asset['id']}", json={"name": "probe"}, headers=_write_headers(csrf, workspace_a)
        )
    ).status_code == 404
    assert (
        await workspace_client.delete(f"/assets/{legacy_asset['id']}", headers=_write_headers(csrf, workspace_a))
    ).status_code == 404
    assert (
        await workspace_client.patch(
            f"/crypto/portfolios/{legacy_crypto['id']}",
            json={"name": "probe"},
            headers=_write_headers(csrf, workspace_a),
        )
    ).status_code == 404

    # Auth-disabled path keeps the original installation-wide behavior: it
    # sees the legacy rows *and* the workspace-scoped one.
    legacy_view = (await client.get("/assets")).json()
    assert {row["id"] for row in legacy_view} == {legacy_asset["id"], scoped_asset["id"]}
    assert [row["id"] for row in (await client.get("/crypto/portfolios")).json()] == [legacy_crypto["id"]]
    assert [row["id"] for row in (await client.get("/investments/portfolios")).json()] == [
        legacy_investment["id"]
    ]