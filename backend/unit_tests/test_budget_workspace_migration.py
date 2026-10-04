"""Owned disposable database checks for category-budget ownership."""
import asyncio
from uuid import uuid4

from unit_tests.test_core_workspace_migration import (
    _alembic, _create_database, _drop_database, _execute, _fetch_values, _owned_databases,
)

REVISION = 'e3b7c9d2a105'
CORE = 'd2f6a8c1e940'


def test_budget_migration_roundtrip_and_populated_rollback():
    databases = ['aurum_core_test_' + uuid4().hex for _ in range(2)]
    empty, populated = databases
    try:
        for db in databases:
            asyncio.run(_create_database(db))
            _alembic(db, 'upgrade', CORE)
        _alembic(empty, 'upgrade', REVISION)
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('budgets_category_scope', 'budgets_budget_immutable_scope', 'categories_budget_immutable_scope')")) == [3]
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('transaction_tags_scope', 'transactions_immutable_scope', 'tags_immutable_scope')")) == [3]
        assert asyncio.run(_fetch_values(empty, 'SELECT version_num FROM alembic_version')) == [REVISION]
        assert asyncio.run(_fetch_values(empty, "SELECT is_nullable FROM information_schema.columns WHERE table_name='budgets' AND column_name='workspace_id'")) == ['YES']
        _alembic(empty, 'downgrade', CORE)
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('budgets_category_scope', 'budgets_budget_immutable_scope', 'categories_budget_immutable_scope')")) == [0]
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_proc WHERE proname IN ('enforce_budget_category_scope', 'protect_budget_category_scope')")) == [0]
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM information_schema.columns WHERE table_name='budgets' AND column_name='workspace_id'")) == [0]
        _alembic(empty, 'upgrade', REVISION)
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('budgets_category_scope', 'budgets_budget_immutable_scope', 'categories_budget_immutable_scope')")) == [3]
        assert asyncio.run(_fetch_values(empty, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('transaction_tags_scope', 'transactions_immutable_scope', 'tags_immutable_scope')")) == [3]
        assert asyncio.run(_fetch_values(empty, 'SELECT version_num FROM alembic_version')) == [REVISION]
        asyncio.run(_execute(populated, "INSERT INTO categories (name, kind, color, sort_order, is_default) VALUES ('Legacy budget', 'EXPENSE', '#123456', 0, false)"))
        asyncio.run(_execute(populated, "INSERT INTO budgets (category_id, monthly_limit) SELECT id, 100 FROM categories"))
        failed = _alembic(populated, 'upgrade', REVISION, check=False)
        assert failed.returncode != 0
        assert 'budget workspace isolation requires empty budgets' in failed.stdout + failed.stderr
        assert asyncio.run(_fetch_values(populated, 'SELECT version_num FROM alembic_version')) == [CORE]
        assert asyncio.run(_fetch_values(populated, 'SELECT monthly_limit FROM budgets')) == [100]
        assert asyncio.run(_fetch_values(populated, "SELECT count(*) FROM information_schema.columns WHERE table_name='budgets' AND column_name='workspace_id'")) == [0]
    finally:
        for db in databases:
            if db in _owned_databases:
                asyncio.run(_drop_database(db))
