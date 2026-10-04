"""Owned disposable database checks for category-budget ownership."""
import asyncio
from uuid import uuid4

from unit_tests.test_core_workspace_migration import (
    _alembic, _create_database, _drop_database, _execute, _fetch_values, _owned_databases, _url,
)

REVISION = 'e3b7c9d2a105'
CORE = 'd2f6a8c1e940'


def test_budget_migration_roundtrip_and_populated_compatibility():
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
        upgraded = _alembic(populated, 'upgrade', REVISION, check=False)
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        assert asyncio.run(_fetch_values(populated, 'SELECT version_num FROM alembic_version')) == [REVISION]
        assert asyncio.run(_fetch_values(populated, 'SELECT monthly_limit FROM budgets WHERE workspace_id IS NULL')) == [100]
    finally:
        for db in databases:
            if db in _owned_databases:
                asyncio.run(_drop_database(db))


def test_budget_migration_rejects_scoped_category_before_alter_and_rolls_back():
    """A legacy budget cannot silently inherit an existing category's owner."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    database = 'aurum_core_test_' + uuid4().hex
    user, workspace, membership = uuid4(), uuid4(), uuid4()

    async def fixture():
        engine = create_async_engine(_url(database))
        try:
            async with engine.begin() as connection:
                statements = [
                    f"INSERT INTO users (id, normalized_login, display_name, status, password_hash) VALUES ('{user}', 'fixture.invalid', 'Fixture', 'disabled', 'not-a-credential')",
                    f"INSERT INTO workspaces (id, kind, display_name, created_by_user_id, personal_owner_user_id) VALUES ('{workspace}', 'personal', 'Fixture', '{user}', '{user}')",
                    f"INSERT INTO workspace_memberships (id, workspace_id, user_id, role) VALUES ('{membership}', '{workspace}', '{user}', 'owner')",
                    f"UPDATE users SET personal_workspace_id='{workspace}' WHERE id='{user}'",
                    f"INSERT INTO categories (workspace_id, name, kind, color, sort_order, is_default) VALUES ('{workspace}', 'Scoped fixture', 'EXPENSE', '#123456', 7, false)",
                    "INSERT INTO budgets (category_id, monthly_limit) SELECT id, 123.45 FROM categories",
                ]
                for statement in statements:
                    await connection.execute(text(statement))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_create_database(database))
        _alembic(database, 'upgrade', CORE)
        asyncio.run(fixture())
        before = asyncio.run(_fetch_values(database, "SELECT row_to_json(b)::text FROM budgets b"))
        failed = _alembic(database, 'upgrade', REVISION, check=False)
        assert failed.returncode != 0
        assert 'budget category workspace mismatch' in failed.stdout + failed.stderr
        assert asyncio.run(_fetch_values(database, 'SELECT version_num FROM alembic_version')) == [CORE]
        assert asyncio.run(_fetch_values(database, "SELECT row_to_json(b)::text FROM budgets b")) == before
        assert asyncio.run(_fetch_values(database, "SELECT workspace_id FROM categories")) == [workspace]
        assert asyncio.run(_fetch_values(database, "SELECT count(*) FROM information_schema.columns WHERE table_name='budgets' AND column_name='workspace_id'")) == [0]
        assert asyncio.run(_fetch_values(database, "SELECT count(*) FROM pg_constraint WHERE conname='uq_budgets_category_id'")) == [1]
        assert asyncio.run(_fetch_values(database, "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname='budgets_category_scope'")) == [0]
        # A retry is also fail-closed, with no partial ALTER or inferred owner.
        assert _alembic(database, 'upgrade', REVISION, check=False).returncode != 0
        assert asyncio.run(_fetch_values(database, "SELECT row_to_json(b)::text FROM budgets b")) == before
    finally:
        if database in _owned_databases:
            asyncio.run(_drop_database(database))
