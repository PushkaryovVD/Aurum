"""Database regressions for compatibility and scoped transaction tags."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.tag import Tag
from app.models.transaction import Transaction
from tests.test_core_workspace_isolation import (  # noqa: F401
    _bootstrap_user, _create_core_records, _login, _write_headers,
    workspace_auth_settings, workspace_client,
)


async def _scoped_records(client, sessionmaker):
    _, local = await _bootstrap_user(sessionmaker, "local-invariant@example.com")
    _, foreign = await _bootstrap_user(sessionmaker, "foreign-invariant@example.com")
    csrf = await _login(client, "foreign-invariant@example.com")
    other = await _create_core_records(client, csrf, foreign, "foreign")
    client.cookies.clear()
    csrf = await _login(client, "local-invariant@example.com")
    own = await _create_core_records(client, csrf, local, "own")
    return local, foreign, csrf, own, other


async def test_scoped_external_id_uniqueness_and_null_semantics(workspace_client, test_sessionmaker):
    local, foreign, _, own, other = await _scoped_records(workspace_client, test_sessionmaker)
    def transaction(scope, account, external_id):
        return Transaction(workspace_id=scope, account_id=account, type="expense",
            amount=Decimal("1"), transaction_amount=Decimal("1"), currency="KZT",
            date=date(2026, 1, 15), description="Scoped uniqueness", external_id=external_id)
    async with test_sessionmaker() as session:
        session.add_all([transaction(local, own["account"]["id"], None),
                         transaction(local, own["account"]["id"], None),
                         transaction(local, own["account"]["id"], "scoped-key"),
                         transaction(foreign, other["account"]["id"], "scoped-key")])
        await session.commit()
        session.add(transaction(local, own["account"]["id"], "scoped-key"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_authenticated_secondary_insert_populates_scope(workspace_client, test_sessionmaker):
    local, _, _, own, _ = await _scoped_records(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        scope = (await session.execute(text(
            "SELECT workspace_id FROM transaction_tags WHERE transaction_id=:id"
        ), {"id": own["transaction"]["id"]})).scalar_one()
        assert scope == local


@pytest.mark.parametrize("explicit_scope", [False, True])
async def test_database_rejects_cross_workspace_tag_link(workspace_client, test_sessionmaker, explicit_scope):
    local, _, _, own, other = await _scoped_records(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        with pytest.raises(DBAPIError):
            await session.execute(text(
                "INSERT INTO transaction_tags (transaction_id, tag_id, workspace_id) VALUES (:tx, :tag, :scope)"
            ), {"tx": own["transaction"]["id"], "tag": other["tag"]["id"],
                "scope": local if explicit_scope else None})
            await session.commit()


async def test_foreign_tag_is_not_eager_loaded_from_corrupt_link(workspace_client, test_sessionmaker):
    local, _, _, own, other = await _scoped_records(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        # Simulate historical corruption as the disposable cluster's superuser;
        # the normal write path is separately tested to reject this state.
        await session.execute(text("SET LOCAL session_replication_role = replica"))
        await session.execute(text(
            "INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (:tx, :tag)"
        ), {"tx": own["transaction"]["id"], "tag": other["tag"]["id"]})
        await session.commit()
    response = await workspace_client.get("/transactions", headers={"X-Aurum-Workspace": str(local)})
    assert response.status_code == 200
    assert [tag["id"] for tag in response.json()["items"][0]["tags"]] == [own["tag"]["id"]]


async def test_null_workspace_tag_names_remain_unique(test_sessionmaker):
    async with test_sessionmaker() as session:
        session.add(Tag(name="Compatibility duplicate"))
        await session.commit()
        session.add(Tag(name="Compatibility duplicate"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_null_workspace_external_ids_remain_unique(test_sessionmaker, account_id):
    def transaction(external_id):
        return Transaction(account_id=account_id, type="expense", amount=Decimal("1"),
                           transaction_amount=Decimal("1"), currency="KZT", date=date(2026, 1, 15),
                           description="Compatibility", external_id=external_id)
    async with test_sessionmaker() as session:
        session.add_all([transaction(None), transaction(None), transaction("same")])
        await session.commit()
        session.add(transaction("same"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.parametrize("table,record", [("tags", "tag"), ("transactions", "transaction")])
async def test_parent_workspace_update_cannot_invalidate_links(workspace_client, test_sessionmaker, table, record):
    _, foreign, _, own, _ = await _scoped_records(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text(f"UPDATE {table} SET workspace_id=:scope WHERE id=:id"),
                                  {"scope": foreign, "id": own[record]["id"]})
            await session.commit()


async def test_association_update_cannot_link_foreign_tag(workspace_client, test_sessionmaker):
    _, _, _, own, other = await _scoped_records(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text("UPDATE transaction_tags SET tag_id=:tag WHERE transaction_id=:tx"),
                                  {"tag": other["tag"]["id"], "tx": own["transaction"]["id"]})
            await session.commit()


async def test_same_workspace_tag_crud_and_secondary_updates(workspace_client, test_sessionmaker):
    local, foreign, csrf, own, _ = await _scoped_records(workspace_client, test_sessionmaker)
    headers = _write_headers(csrf, local)
    added = await workspace_client.post("/tags", json={"name": "Replacement"}, headers=headers)
    assert added.status_code == 201
    dedup = await workspace_client.post("/tags", json={"name": "replacement"}, headers=headers)
    assert dedup.json()["id"] == added.json()["id"]
    updated = await workspace_client.patch(f"/transactions/{own['transaction']['id']}",
        json={"tag_ids": [added.json()["id"]]}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert [tag["id"] for tag in updated.json()["tags"]] == [added.json()["id"]]
    async with test_sessionmaker() as session:
        assert (await session.execute(text("SELECT workspace_id FROM transaction_tags WHERE transaction_id=:tx"),
                                      {"tx": own["transaction"]["id"]})).scalar_one() == local
    # A duplicate name in another namespace is legal, and remains private.
    async with test_sessionmaker() as session:
        session.add(Tag(name="Replacement", workspace_id=foreign))
        await session.commit()
    assert (await workspace_client.delete(f"/tags/{added.json()['id']}", headers=headers)).status_code == 204
    page = await workspace_client.get("/transactions", headers={"X-Aurum-Workspace": str(local)})
    assert page.json()["items"][0]["tags"] == []


async def test_null_scope_secondary_insert_remains_valid(client, test_sessionmaker, account_id):
    tag = (await client.post("/tags", json={"name": "Compatibility"})).json()
    response = await client.post("/transactions", json={"account_id": account_id,
        "tag_ids": [tag["id"]], "type": "expense", "amount": "1", "date": "2026-01-15",
        "description": "Compatibility"})
    assert response.status_code == 201, response.text
    async with test_sessionmaker() as session:
        assert (await session.execute(text("SELECT workspace_id FROM transaction_tags"))).scalar_one() is None


@pytest.mark.parametrize("direction", ["scoped_transaction", "scoped_tag"])
async def test_null_and_scoped_namespaces_cannot_be_linked(workspace_client, test_sessionmaker, client, account_id, direction):
    _, _, _, own, _ = await _scoped_records(workspace_client, test_sessionmaker)
    tag = (await client.post("/tags", json={"name": "Compatibility"})).json()
    transaction = (await client.post("/transactions", json={"account_id": account_id,
        "type": "expense", "amount": "1", "date": "2026-01-15", "description": "Compatibility"})).json()
    tx_id = own["transaction"]["id"] if direction == "scoped_transaction" else transaction["id"]
    tag_id = tag["id"] if direction == "scoped_transaction" else own["tag"]["id"]
    async with test_sessionmaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text("INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (:tx, :tag)"),
                                  {"tx": tx_id, "tag": tag_id})
            await session.commit()
