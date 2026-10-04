"""Populated pre-workspace installations must upgrade without assigning owners.

Uses only explicitly owned disposable databases; never application data. The
initial seeded tracer caught the blocking guard before preservation was added.
"""
import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from unit_tests.test_core_workspace_migration import (
    CORE_TABLES, _alembic, _create_database, _drop_database, _execute,
    _fetch_values, _owned_databases, _url,
)

LEGACY = "f0c9a4e1b672"


async def _snapshot(database, columns=None):
    """Capture native values (including Decimal), all old columns, all rows."""
    engine = create_async_engine(_url(database))
    try:
        async with engine.connect() as connection:
            if columns is None:
                columns = {}
                rows = await connection.execute(text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name <> 'alembic_version' "
                    "ORDER BY table_name, ordinal_position"
                ))
                for table, column in rows:
                    columns.setdefault(table, []).append(column)
            data = {}
            for table, names in columns.items():
                projection = ', '.join(f'"{name}"' for name in names)
                data[table] = list((await connection.execute(text(
                    f'SELECT {projection} FROM "{table}" ORDER BY {projection}'
                ))).all())
            return columns, data
    finally:
        await engine.dispose()


async def _startup_seed(database):
    from app.db.seed import (
        seed_default_account, seed_default_app_settings, seed_default_categories,
    )
    engine = create_async_engine(_url(database))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await seed_default_categories(session)
            await seed_default_account(session)
            await seed_default_app_settings(session)
    finally:
        await engine.dispose()


def test_seeded_legacy_installation_upgrades_to_head():
    database = "aurum_core_test_" + uuid4().hex
    try:
        asyncio.run(_create_database(database))
        _alembic(database, "upgrade", LEGACY)
        # Generic first-boot-shaped fixtures, not a user's financial data.
        asyncio.run(_execute(database, "INSERT INTO categories "
            "(name, kind, icon, color, sort_order, is_default) VALUES "
            "('Groceries', 'EXPENSE', 'shopping-basket', '#1baf7a', 0, true)"))
        asyncio.run(_execute(database, "INSERT INTO accounts "
            "(name, type, currency, color, is_archived) VALUES "
            "('Main Account', 'CHECKING', 'KZT', '#2a78d6', false)"))
        upgraded = _alembic(database, "upgrade", "head", check=False)
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        assert asyncio.run(_fetch_values(database,
            "SELECT count(*) FROM categories WHERE workspace_id IS NULL")) == [1]
        assert asyncio.run(_fetch_values(database,
            "SELECT count(*) FROM accounts WHERE workspace_id IS NULL")) == [1]
        assert asyncio.run(_fetch_values(database, "SELECT count(*) FROM users")) == [0]
        assert asyncio.run(_fetch_values(database, "SELECT count(*) FROM workspaces")) == [0]
    finally:
        if database in _owned_databases:
            asyncio.run(_drop_database(database))


def test_populated_legacy_values_links_and_startup_are_preserved():
    database = "aurum_core_test_" + uuid4().hex
    statements = [
        "INSERT INTO categories (id, name, kind, icon, color, sort_order, is_default) VALUES (1, 'Fixture parent', 'EXPENSE', 'tree', '#123456', 23, true)",
        "INSERT INTO categories (id, parent_id, name, kind, icon, color, sort_order, is_default) VALUES (2, 1, 'Fixture child', 'EXPENSE', 'leaf', '#654321', 31, false)",
        "INSERT INTO accounts (id, name, type, currency, color, is_archived) VALUES (1, 'Fixture cash', 'CHECKING', 'KZT', '#112233', false), (2, 'Fixture archive', 'SAVINGS', 'USD', '#332211', true)",
        "INSERT INTO transactions (id, account_id, category_id, type, amount, currency, transaction_amount, description, merchant, notes, date, external_id) VALUES (1, 1, 1, 'EXPENSE', 12345.67, 'USD', 25.13, 'Synthetic expense', 'Fixture merchant', 'Fixture note', '2026-01-02', 'fixture-external-1')",
        "INSERT INTO transactions (id, account_id, transfer_account_id, type, amount, currency, transaction_amount, description, date, external_id) VALUES (2, 1, 2, 'TRANSFER', 10.01, 'KZT', 10.01, 'Synthetic transfer', '2026-01-03', NULL)",
        "INSERT INTO transaction_splits (id, transaction_id, category_id, amount, note) VALUES (1, 1, 2, 12000.01, 'Fixture split'), (2, 1, 1, 345.66, 'Fixture remainder')",
        "INSERT INTO tags (id, name) VALUES (1, 'fixture-tag'), (2, 'fixture-other-tag')",
        "INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (1, 1), (1, 2), (2, 1)",
        "INSERT INTO budgets (id, category_id, monthly_limit) VALUES (1, 1, 22222.29), (2, 2, 111.11)",
        "INSERT INTO app_settings (id, currency, negative_cash_flow_threshold_months, net_worth_decline_threshold_months, risky_allocation_threshold_percent, idle_cash_threshold_amount, idle_cash_threshold_days) VALUES (1, 'KZT', 3, 4, 37, 87654.32, 91)",
        "INSERT INTO goals (id, name, target_amount, target_date) VALUES (1, 'Fixture goal', 98765.43, '2027-01-01')",
        "INSERT INTO goal_contributions (id, goal_id, amount, date, note) VALUES (1, 1, 765.43, '2026-01-04', 'Fixture contribution')",
        "INSERT INTO assets (id, name, asset_class, currency, capital_role, monthly_cash_flow, risk_level, valuation_mode) VALUES (1, 'Fixture asset', 'OTHER', 'KZT', 'NEUTRAL', 12.34, 'MEDIUM', 'MANUAL_ONLY')",
        "INSERT INTO asset_valuations (id, asset_id, value, as_of_date) VALUES (1, 1, 54321.09, '2026-01-05')",
    ]
    try:
        asyncio.run(_create_database(database))
        _alembic(database, "upgrade", LEGACY)
        for statement in statements:
            asyncio.run(_execute(database, statement))
        columns, before = asyncio.run(_snapshot(database))
        assert asyncio.run(_fetch_values(database, 'SELECT amount FROM transactions WHERE id=1')) == [Decimal('12345.67')]
        for _ in range(2):
            _alembic(database, 'upgrade', 'head')
            assert asyncio.run(_snapshot(database, columns))[1] == before
        for _ in range(2):
            asyncio.run(_startup_seed(database))
            assert asyncio.run(_snapshot(database, columns))[1] == before
        for table in (*CORE_TABLES, 'budgets'):
            assert asyncio.run(_fetch_values(database, f'SELECT count(*) FROM {table} WHERE workspace_id IS NOT NULL')) == [0]
        assert asyncio.run(_fetch_values(database, 'SELECT count(*) FROM transactions WHERE author_user_id IS NOT NULL')) == [0]
        for table in ('users', 'workspaces', 'workspace_memberships', 'user_sessions'):
            assert asyncio.run(_fetch_values(database, f'SELECT count(*) FROM {table}')) == [0]
        # Replaced nullable UNIQUE keys still protect the legacy namespace.
        for constraint, statement in (
            ('uq_tags_unscoped_name', "INSERT INTO tags (id, name) VALUES (100, 'fixture-tag')"),
            ('uq_budgets_unscoped_category', "INSERT INTO budgets (id, category_id, monthly_limit) VALUES (100, 1, 1.01)"),
            ('uq_transactions_unscoped_account_external_id', "INSERT INTO transactions (id, account_id, type, amount, currency, transaction_amount, description, date, external_id) VALUES (100, 1, 'EXPENSE', 1.01, 'KZT', 1.01, 'Duplicate fixture', '2026-01-02', 'fixture-external-1')"),
        ):
            with pytest.raises(IntegrityError, match=constraint):
                asyncio.run(_execute(database, statement))
            assert asyncio.run(_snapshot(database, columns))[1] == before
    finally:
        if database in _owned_databases:
            asyncio.run(_drop_database(database))
