"""Category-budget isolation using the server-authorized workspace."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.test_core_workspace_isolation import (
    _bootstrap_user, _create_core_records, _login, _write_headers,
    workspace_auth_settings, workspace_client,
)


async def _two_scopes(client, maker):
    user, personal = await _bootstrap_user(maker, "budget-owner@example.com")
    household = uuid4()
    async with maker() as session:
        await session.execute(text("INSERT INTO workspaces (id, kind, display_name, created_by_user_id) VALUES (:w, 'household', 'Budget household', :u)"), {"w": household, "u": user})
        await session.execute(text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :w, :u, 'owner')"), {"id": uuid4(), "w": household, "u": user})
        await session.commit()
    csrf = await _login(client, "budget-owner@example.com")
    first = await _create_core_records(client, csrf, personal, "personal")
    second = await _create_core_records(client, csrf, household, "household")
    return csrf, personal, household, first, second


async def test_budget_reads_and_mutations_are_scoped(workspace_client, test_sessionmaker):
    client = workspace_client
    csrf, personal, household, first, second = await _two_scopes(client, test_sessionmaker)
    ph, hh = _write_headers(csrf, personal), _write_headers(csrf, household)
    response = await client.post('/budgets', json={'category_id': first['category']['id'], 'monthly_limit': '100'}, headers=ph)
    assert response.status_code == 201, response.text
    budget = response.json()['id']
    assert (await client.get('/budgets', headers=hh)).json() == []
    assert (await client.get('/budgets/status?year=2026&month=1', headers=hh)).json()['items'] == []
    for method in ('patch', 'delete'):
        kwargs = {'json': {'monthly_limit': '200'}} if method == 'patch' else {}
        assert (await getattr(client, method)(f'/budgets/{budget}', headers=hh, **kwargs)).status_code == 404
    for foreign in (first['category']['id'], 999999):
        response = await client.post('/budgets', json={'category_id': foreign, 'monthly_limit': '100'}, headers=hh)
        assert response.status_code == 400
        assert response.json() == {'detail': 'Category not found'}
    response = await client.post('/budgets', json={'category_id': second['category']['id'], 'monthly_limit': '100'}, headers=hh)
    assert response.status_code == 201
    assert len((await client.get('/budgets', headers=ph)).json()) == 1
    assert (await client.patch(f'/budgets/{budget}', json={'monthly_limit': '150'}, headers=ph)).status_code == 200
    assert (await client.delete(f'/budgets/{budget}', headers=ph)).status_code == 204
    assert (await client.get('/budgets', headers=ph)).json() == []


async def test_household_status_excludes_private_plain_and_split_sources(workspace_client, test_sessionmaker):
    client = workspace_client
    csrf, personal, household, first, second = await _two_scopes(client, test_sessionmaker)
    hh = _write_headers(csrf, household)
    category = second['category']['id']
    response = await client.post('/budgets', json={'category_id': category, 'monthly_limit': '100'}, headers=hh)
    assert response.status_code == 201
    async with test_sessionmaker() as session:
        # Deliberately inconsistent legacy sources exercise all aggregation
        # boundaries, not merely category-ID separation on clean API writes.
        for scope, account, split_scope, amount, base in (
            (personal, first['account']['id'], None, '900', None),
            (personal, first['account']['id'], personal, '800', None),
            (household, first['account']['id'], None, '700', None),
            (household, second['account']['id'], personal, '600', None),
            (household, second['account']['id'], household, '20', None),
            (household, second['account']['id'], None, '50', '0'),
        ):
            txn = (await session.execute(text("INSERT INTO transactions (workspace_id, account_id, category_id, type, amount, currency, transaction_amount, description, date, purpose, base_amount_kzt) VALUES (:w, :a, :c, 'EXPENSE', :v, 'KZT', :v, 'Synthetic budget source', '2026-01-15', 'ORDINARY', :b) RETURNING id"), {'w': scope, 'a': account, 'c': category if split_scope is None else None, 'v': Decimal(amount), 'b': Decimal(base) if base is not None else None})).scalar_one()
            if split_scope is not None:
                await session.execute(text('INSERT INTO transaction_splits (transaction_id, workspace_id, category_id, amount) VALUES (:t, :w, :c, :v)'), {'t': txn, 'w': split_scope, 'c': category, 'v': Decimal(amount)})
        await session.commit()
    items = (await client.get('/budgets/status?year=2026&month=1', headers=hh)).json()['items']
    assert len(items) == 1
    assert Decimal(items[0]['spent']) == Decimal('20.01')
    assert Decimal(items[0]['remaining']) == Decimal('79.99')


@pytest.mark.parametrize('budget_namespace,category_namespace', [('personal', 'household'), ('personal', None), (None, 'household')])
async def test_database_rejects_budget_category_namespace_mismatch(workspace_client, test_sessionmaker, budget_namespace, category_namespace):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    scopes = {'personal': personal, 'household': household, None: None}
    async with test_sessionmaker() as session:
        category = second['category']['id'] if category_namespace == 'household' else (await session.execute(text('SELECT id FROM categories WHERE workspace_id IS NULL LIMIT 1'))).scalar_one()
        with pytest.raises(IntegrityError, match='budget category workspace mismatch'):
            await session.execute(text('INSERT INTO budgets (workspace_id, category_id, monthly_limit) VALUES (:w, :c, 100)'), {'w': scopes[budget_namespace], 'c': category})
        await session.rollback()


@pytest.mark.parametrize('table', ['categories', 'budgets'])
async def test_budget_relation_parent_scope_cannot_be_changed(workspace_client, test_sessionmaker, table):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    category = second['category']['id']
    response = await workspace_client.post('/budgets', json={'category_id': category, 'monthly_limit': '100'}, headers=_write_headers(csrf, household))
    assert response.status_code == 201
    target = category if table == 'categories' else response.json()['id']
    async with test_sessionmaker() as session:
        with pytest.raises(IntegrityError, match='budget/category workspace is immutable'):
            await session.execute(text(f'UPDATE {table} SET workspace_id=:w WHERE id=:id'), {'w': personal, 'id': target})
        await session.rollback()


@pytest.mark.parametrize('role,allowed', [('viewer', False), ('editor', True)])
async def test_budget_membership_role_controls_writes(workspace_client, test_sessionmaker, role, allowed):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    headers = _write_headers(csrf, household)
    existing = await workspace_client.post('/budgets', json={'category_id': second['category']['id'], 'monthly_limit': '100'}, headers=headers)
    assert existing.status_code == 201
    user, _ = await _bootstrap_user(test_sessionmaker, 'budget-member@example.com')
    async with test_sessionmaker() as session:
        await session.execute(text('INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :w, :u, :r)'), {'id': uuid4(), 'w': household, 'u': user, 'r': role})
        await session.commit()
    csrf = await _login(workspace_client, 'budget-member@example.com')
    headers = _write_headers(csrf, household)
    assert (await workspace_client.get('/budgets', headers=headers)).status_code == 200
    assert (await workspace_client.get('/budgets/status?year=2026&month=1', headers=headers)).status_code == 200
    response = await workspace_client.patch(f"/budgets/{existing.json()['id']}", json={'monthly_limit': '200'}, headers=headers)
    assert response.status_code == (200 if allowed else 403)
    response = await workspace_client.delete(f"/budgets/{existing.json()['id']}", headers=headers)
    assert response.status_code == (204 if allowed else 403)
    response = await workspace_client.post('/budgets', json={'category_id': second['category']['id'], 'monthly_limit': '100'}, headers=headers)
    assert response.status_code == (201 if allowed else 403)


@pytest.mark.parametrize('namespace', ['scoped', 'legacy'])
async def test_database_budget_uniqueness_and_category_update_guard(workspace_client, test_sessionmaker, namespace):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    async with test_sessionmaker() as session:
        if namespace == 'scoped':
            scope, category = household, second['category']['id']
            foreign = first['category']['id']
        else:
            scope = None
            category = (await session.execute(text('SELECT id FROM categories WHERE workspace_id IS NULL LIMIT 1'))).scalar_one()
            foreign = second['category']['id']
        budget = (await session.execute(text('INSERT INTO budgets (workspace_id, category_id, monthly_limit) VALUES (:w, :c, 100) RETURNING id'), {'w': scope, 'c': category})).scalar_one()
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(text('INSERT INTO budgets (workspace_id, category_id, monthly_limit) VALUES (:w, :c, 200)'), {'w': scope, 'c': category})
        await session.rollback()
        with pytest.raises(IntegrityError, match='budget category workspace mismatch'):
            await session.execute(text('UPDATE budgets SET category_id=:c WHERE id=:id'), {'c': foreign, 'id': budget})
        await session.rollback()
        # Keep the preexisting category-delete UX: its budget cascades away.
        await session.execute(text('DELETE FROM categories WHERE id=:c'), {'c': category})
        await session.commit()
        assert not (await session.execute(text('SELECT id FROM budgets WHERE id=:id'), {'id': budget})).all()


async def test_budget_workspace_selection_requires_active_membership(workspace_client, test_sessionmaker):
    assert (await workspace_client.get('/budgets')).status_code == 401
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    other_user, foreign = await _bootstrap_user(test_sessionmaker, 'foreign-budget-owner@example.com')
    for workspace in (foreign, uuid4()):
        headers = _write_headers(csrf, workspace)
        assert (await workspace_client.get('/budgets', headers=headers)).status_code == 404
        assert (await workspace_client.get('/budgets/status?year=2026&month=1', headers=headers)).status_code == 404
        assert (await workspace_client.post('/budgets', json={'category_id': second['category']['id'], 'monthly_limit': '100'}, headers=headers)).status_code == 404
    async with test_sessionmaker() as session:
        # Keep a second owner active; revoking the last household owner is
        # correctly prohibited by the existing identity foundation.
        await session.execute(text("INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES (:id, :w, :u, 'owner')"), {'id': uuid4(), 'w': household, 'u': other_user})
        await session.execute(text('UPDATE workspace_memberships SET revoked_at=now() WHERE workspace_id=:w AND user_id<>:u'), {'w': household, 'u': other_user})
        await session.commit()
    assert (await workspace_client.get('/budgets', headers=_write_headers(csrf, household))).status_code == 404


async def test_scoped_parent_and_child_budgets_keep_rollup_and_zero_split_snapshot(workspace_client, test_sessionmaker):
    csrf, personal, household, first, second = await _two_scopes(workspace_client, test_sessionmaker)
    headers = _write_headers(csrf, household)
    parent = second['category']['id']
    child_response = await workspace_client.post('/categories', json={'name': 'Synthetic child', 'kind': 'expense', 'color': '#123456', 'parent_id': parent}, headers=headers)
    assert child_response.status_code == 201
    child = child_response.json()['id']
    for category in (parent, child):
        response = await workspace_client.post('/budgets', json={'category_id': category, 'monthly_limit': '100'}, headers=headers)
        assert response.status_code == 201
    response = await workspace_client.post(
        '/transactions',
        json={'account_id': second['account']['id'], 'type': 'expense', 'amount': '30',
              'description': 'Synthetic split', 'date': '2026-01-15',
              'splits': [{'category_id': parent, 'amount': '10'}, {'category_id': child, 'amount': '20'}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    # An explicit zero exchange-rate snapshot is a real zero, not missing.
    async with test_sessionmaker() as session:
        txn = (await session.execute(text("INSERT INTO transactions (workspace_id, account_id, type, amount, currency, transaction_amount, description, date, purpose, exchange_rate_to_kzt) VALUES (:w, :a, 'EXPENSE', 50, 'KZT', 50, 'Synthetic zero snapshot', '2026-01-15', 'ORDINARY', 0) RETURNING id"), {'w': household, 'a': second['account']['id']})).scalar_one()
        await session.execute(text('INSERT INTO transaction_splits (transaction_id, workspace_id, category_id, amount) VALUES (:t, :w, :c, 50)'), {'t': txn, 'w': household, 'c': child})
        # Even a legacy child referencing a scoped parent must not expand
        # the aggregation's category set into the legacy namespace.
        legacy_child = (await session.execute(text("INSERT INTO categories (parent_id, name, kind, color, sort_order, is_default) VALUES (:p, 'Legacy child', 'EXPENSE', '#123456', 0, false) RETURNING id"), {'p': parent})).scalar_one()
        await session.execute(text("INSERT INTO transactions (workspace_id, account_id, category_id, type, amount, currency, transaction_amount, description, date, purpose) VALUES (:w, :a, :c, 'EXPENSE', 500, 'KZT', 500, 'Synthetic mismatched child', '2026-01-15', 'ORDINARY')"), {'w': household, 'a': second['account']['id'], 'c': legacy_child})
        await session.commit()
    items = {item['category_id']: item for item in (await workspace_client.get('/budgets/status?year=2026&month=1', headers=headers)).json()['items']}
    assert Decimal(items[parent]['spent']) == Decimal('30.01')
    assert Decimal(items[child]['spent']) == Decimal('20.00')
