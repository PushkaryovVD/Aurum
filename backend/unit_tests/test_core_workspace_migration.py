"""Disposable PostgreSQL checks for the staged core-workspace migration."""
import asyncio
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from test_support.disposable_postgres import DisposablePostgres

BACKEND_DIR = Path(__file__).resolve().parents[1]
_owned_databases: dict[str, tuple[int, int]] = {}
CORE_TABLES = ("accounts", "categories", "tags", "transactions", "transaction_splits", "transaction_tags")


def _runner() -> DisposablePostgres:
    return DisposablePostgres(prefix="aurum_core_test_", owned=_owned_databases)


def _connection_settings() -> tuple[str, int, str, str]:
    runner = _runner()
    return runner.host, runner.port, runner.user, runner.password


def _url(database: str):
    return _runner().url(database)


async def _verify_cluster(connection) -> None:
    await _runner().verify_cluster(connection)


async def _create_database(database: str) -> None:
    # CREATE-only: a collision must fail, never drop preexisting data.
    await _runner().create(database)


async def _drop_database(database: str) -> None:
    # No FORCE: leaked connections fail cleanup rather than terminate
    # another process. Engines are disposed by every helper above.
    await _runner().drop(database)


async def _fetch_values(database: str, statement: str) -> list[object]:
    engine = create_async_engine(_url(database))
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(text(statement))).scalars())
    finally:
        await engine.dispose()


async def _execute(database: str, statement: str) -> None:
    engine = create_async_engine(_url(database))
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


def _alembic(database: str, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _runner().alembic(database, BACKEND_DIR, *arguments,
                             check=check, capture_output=True)


def _workspace_column_count(database: str) -> int:
    table_names = ", ".join(f"'{table}'" for table in CORE_TABLES)
    values = asyncio.run(
        _fetch_values(
            database,
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'workspace_id' "
            f"AND table_name IN ({table_names})",
        )
    )
    return int(values[0])


def test_core_workspace_migration_roundtrip_and_populated_compatibility() -> None:
    roundtrip_db = "aurum_core_test_" + uuid4().hex
    populated_db = "aurum_core_test_" + uuid4().hex
    try:
        for database in (roundtrip_db, populated_db):
            asyncio.run(_create_database(database))
        _alembic(roundtrip_db, "upgrade", "d2f6a8c1e940")
        assert asyncio.run(_fetch_values(roundtrip_db, "SELECT version_num FROM alembic_version")) == [
            "d2f6a8c1e940"
        ]
        assert _workspace_column_count(roundtrip_db) == len(CORE_TABLES)

        _alembic(roundtrip_db, "downgrade", "9c4e2b7d1a60")
        assert asyncio.run(_fetch_values(roundtrip_db, "SELECT version_num FROM alembic_version")) == [
            "9c4e2b7d1a60"
        ]
        assert _workspace_column_count(roundtrip_db) == 0

        _alembic(roundtrip_db, "upgrade", "d2f6a8c1e940")
        assert asyncio.run(_fetch_values(roundtrip_db, "SELECT version_num FROM alembic_version")) == [
            "d2f6a8c1e940"
        ]
        assert _workspace_column_count(roundtrip_db) == len(CORE_TABLES)

        _alembic(populated_db, "upgrade", "9c4e2b7d1a60")
        asyncio.run(
            _execute(
                populated_db,
                "INSERT INTO accounts (name, type, currency, is_archived) "
                "VALUES ('Legacy account', 'CHECKING', 'KZT', false)",
            )
        )
        upgraded = _alembic(populated_db, "upgrade", "d2f6a8c1e940", check=False)
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        assert asyncio.run(_fetch_values(populated_db, "SELECT version_num FROM alembic_version")) == [
            "d2f6a8c1e940"
        ]
        assert asyncio.run(_fetch_values(populated_db, "SELECT count(*) FROM accounts WHERE workspace_id IS NULL")) == [1]
        assert asyncio.run(_fetch_values(populated_db, "SELECT count(*) FROM users")) == [0]
        assert asyncio.run(_fetch_values(populated_db, "SELECT count(*) FROM workspaces")) == [0]
        assert _workspace_column_count(populated_db) == len(CORE_TABLES)
        asyncio.run(_execute(populated_db, "INSERT INTO tags (name) VALUES ('fixture-unique')"))
        with pytest.raises(IntegrityError, match='uq_tags_unscoped_name'):
            asyncio.run(_execute(populated_db, "INSERT INTO tags (name) VALUES ('fixture-unique')"))
        assert asyncio.run(_fetch_values(populated_db, "SELECT name FROM tags")) == ['fixture-unique']
        _alembic(populated_db, "upgrade", "d2f6a8c1e940")
        assert asyncio.run(_fetch_values(populated_db, "SELECT name FROM tags WHERE workspace_id IS NULL")) == ['fixture-unique']
    finally:
        for database in (roundtrip_db, populated_db):
            if database in _owned_databases:
                asyncio.run(_drop_database(database))
