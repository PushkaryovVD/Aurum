"""Safety boundaries of the explicitly owned disposable migration runner."""
import json
import os
from pathlib import Path

import pytest

from unit_tests import test_core_workspace_migration as migration


def test_explicit_owned_runtime_accepts_provisioned_port():
    assert migration._connection_settings()[:3] == (
        os.environ["AURUM_POSTGRES_HOST"], int(os.environ["AURUM_POSTGRES_PORT"]),
        os.environ["AURUM_POSTGRES_USER"],
    )


def test_missing_runtime_rejects_endpoint(monkeypatch):
    monkeypatch.delenv("AURUM_DISPOSABLE_POSTGRES_RUNTIME", raising=False)
    with pytest.raises((AssertionError, ValueError), match="runtime"):
        migration._connection_settings()


@pytest.mark.parametrize("override", [
    {"disposable": False}, {"host": "192.0.2.1"}, {"port": 1},
    {"user": "unowned"}, {"data": "/not/owned/data"},
])
def test_unowned_runtime_is_rejected(monkeypatch, tmp_path, override):
    runtime = json.loads(Path(os.environ["AURUM_DISPOSABLE_POSTGRES_RUNTIME"]).read_text())
    runtime.update(override)
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(runtime))
    monkeypatch.setenv("AURUM_DISPOSABLE_POSTGRES_RUNTIME", str(path))
    with pytest.raises((AssertionError, ValueError)):
        migration._connection_settings()

def test_create_collision_keeps_existing_database_intact():
    import asyncio
    from uuid import uuid4
    from sqlalchemy.exc import DBAPIError
    database = "aurum_core_test_" + uuid4().hex
    asyncio.run(migration._create_database(database))
    try:
        original_oid = migration._owned_databases[database]
        asyncio.run(migration._execute(database, "CREATE TABLE sentinel (value integer)"))
        asyncio.run(migration._execute(database, "INSERT INTO sentinel VALUES (42)"))
        with pytest.raises(DBAPIError):
            asyncio.run(migration._create_database(database))
        assert migration._owned_databases[database] == original_oid
        assert asyncio.run(migration._fetch_values(database, "SELECT value FROM sentinel")) == [42]
    finally:
        asyncio.run(migration._drop_database(database))


def test_unowned_database_drop_and_migration_are_rejected():
    import asyncio
    with pytest.raises(ValueError, match="not created"):
        asyncio.run(migration._drop_database("aurum"))
    with pytest.raises(ValueError, match="owned"):
        migration._alembic("aurum", "upgrade", "head")
