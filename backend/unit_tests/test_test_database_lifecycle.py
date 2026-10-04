"""Fail-closed regression checks; negative paths never contact PostgreSQL."""
import asyncio
import json
import subprocess
import sys
from uuid import uuid4

from test_support import disposable_postgres as lifecycle
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[1] / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("lifecycle_conftest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_fixture_requires_explicit_runtime(harness, monkeypatch):
    monkeypatch.delenv("AURUM_DISPOSABLE_POSTGRES_RUNTIME", raising=False)

    def forbidden_connection(*args, **kwargs):
        pytest.fail("database connection attempted without owned runtime")

    monkeypatch.setattr(harness, "create_async_engine", forbidden_connection)
    fixture = harness._test_database.__wrapped__()
    with pytest.raises(ValueError, match="runtime"):
        next(fixture)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "PG_VERSION").write_text("17")
    metadata = {"workspace": str(tmp_path), "data": str(data), "host": "127.0.0.1",
                "port": 57613, "user": "postgres", "disposable": True}
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(metadata))
    for key, value in {"AURUM_DISPOSABLE_POSTGRES_RUNTIME": str(path),
                       "AURUM_POSTGRES_HOST": "127.0.0.1", "AURUM_POSTGRES_PORT": "57613",
                       "AURUM_POSTGRES_USER": "postgres", "AURUM_POSTGRES_PASSWORD": ""}.items():
        monkeypatch.setenv(key, value)
    return lifecycle.DisposablePostgres()


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def one_or_none(self):
        return self.value


class FakeEngine:
    def __init__(self, runtime):
        self.data = str(runtime.data)
        self.user = runtime.user
        self.database_identity = (42, 7)
        self.collision = False
        self.statements = []
        self.disposed = 0

    def connect(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def dispose(self):
        self.disposed += 1

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append(sql)
        if sql == "SHOW data_directory":
            return Result(self.data)
        if sql == "SELECT current_user":
            return Result(self.user)
        if sql.startswith("SELECT oid, datdba"):
            return Result(self.database_identity)
        if sql.startswith("CREATE DATABASE") and self.collision:
            raise RuntimeError("database already exists")
        return Result(None)


@pytest.fixture
def fake_engine(runtime, monkeypatch):
    engine = FakeEngine(runtime)
    monkeypatch.setattr(lifecycle, "create_async_engine", lambda *a, **kw: engine)
    return engine


@pytest.mark.parametrize("host", ["192.0.2.1", "localhost", "::1", "db"])
def test_remote_or_unverified_hostname_rejected_before_connection(runtime, monkeypatch, host):
    monkeypatch.setenv("AURUM_POSTGRES_HOST", host)
    monkeypatch.setattr(lifecycle, "create_async_engine", lambda *a, **kw: pytest.fail("connection"))
    with pytest.raises(ValueError, match="loopback"):
        lifecycle.DisposablePostgres()


def test_live_data_directory_mismatch_blocks_create(runtime, fake_engine):
    fake_engine.data = "/unowned/data"
    with pytest.raises(ValueError, match="data directory"):
        asyncio.run(runtime.create())
    assert not any(sql.startswith(("CREATE", "DROP")) for sql in fake_engine.statements)
    assert fake_engine.disposed == 1
    assert not runtime.owned


def test_collision_never_drops_or_claims_existing_database(runtime, fake_engine):
    fake_engine.collision = True
    with pytest.raises(RuntimeError, match="already exists"):
        asyncio.run(runtime.create())
    assert not any(sql.startswith("DROP") for sql in fake_engine.statements)
    assert not runtime.owned
    assert fake_engine.disposed == 1


def test_unowned_database_is_never_opened_or_dropped(runtime, monkeypatch):
    monkeypatch.setattr(lifecycle, "create_async_engine", lambda *a, **kw: pytest.fail("connection"))
    with pytest.raises(ValueError, match="not created"):
        asyncio.run(runtime.drop("aurum_test"))
    with pytest.raises(ValueError, match="not owned"):
        runtime.migrate("aurum", Path.cwd())


@pytest.mark.parametrize("database", ["postgres", "aurum", "aurum_fixture_test_" + "a" * 32])
@pytest.mark.parametrize("entrypoint", ["migrate", "alembic", "core_wrapper"])
def test_all_migration_entrypoints_refuse_unowned_targets(runtime, monkeypatch, database, entrypoint):
    calls = []
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(lifecycle, "create_async_engine", lambda *a, **kw: pytest.fail("connection"))
    try:
        with pytest.raises(ValueError, match="not owned"):
            if entrypoint == "migrate":
                runtime.migrate(database, Path.cwd())
            elif entrypoint == "alembic":
                runtime.alembic(database, Path.cwd(), "downgrade", "base", check=False)
            else:
                from unit_tests import test_core_workspace_migration as migration
                migration._alembic(database, "upgrade", "head", check=False)
    finally:
        assert calls == [], "unowned migration dispatched a subprocess"
    assert runtime.url("postgres").database == "postgres"


@pytest.mark.parametrize("identity", [None, (43, 7), (42, 8)])
def test_replaced_oid_or_owner_blocks_cleanup(runtime, fake_engine, identity):
    database = asyncio.run(runtime.create())
    fake_engine.database_identity = identity
    with pytest.raises(ValueError, match="replaced or unowned"):
        asyncio.run(runtime.drop(database))
    assert not any(sql.startswith("DROP") for sql in fake_engine.statements)
    assert database in runtime.owned
    assert fake_engine.disposed == 2


def test_live_cluster_mismatch_also_blocks_cleanup(runtime, fake_engine):
    database = asyncio.run(runtime.create())
    fake_engine.data = "/unowned/data"
    with pytest.raises(ValueError, match="data directory"):
        asyncio.run(runtime.drop(database))
    assert not any(sql.startswith("DROP") for sql in fake_engine.statements)
    assert database in runtime.owned


def test_unique_create_only_and_drop_without_force(runtime, fake_engine):
    first = asyncio.run(runtime.create())
    second = asyncio.run(runtime.create())
    assert first != second
    assert first.startswith("aurum_fixture_test_")
    assert runtime.owned[first] == (42, 7)
    asyncio.run(runtime.drop(first))
    asyncio.run(runtime.drop(second))
    assert not runtime.owned
    assert fake_engine.disposed == 4
    assert all("FORCE" not in sql and "IF EXISTS" not in sql for sql in fake_engine.statements)


def test_migration_failure_cleans_created_database_before_yield(harness, runtime, fake_engine, monkeypatch):
    monkeypatch.setattr(harness, "DisposablePostgres", lambda: runtime)

    def failing_migration(*args):
        raise subprocess.CalledProcessError(1, "alembic")

    monkeypatch.setattr(runtime, "migrate", failing_migration)
    with pytest.raises(subprocess.CalledProcessError):
        next(harness._test_database.__wrapped__())
    assert not runtime.owned
    assert sum(sql.startswith("CREATE DATABASE") for sql in fake_engine.statements) == 1
    assert sum(sql.startswith("DROP DATABASE") for sql in fake_engine.statements) == 1


def test_fixture_teardown_cleans_exact_database(harness, runtime, fake_engine, monkeypatch):
    monkeypatch.setattr(harness, "DisposablePostgres", lambda: runtime)
    monkeypatch.setattr(runtime, "migrate", lambda *a: None)
    fixture = harness._test_database.__wrapped__()
    owner, database = next(fixture)
    assert owner is runtime and database in runtime.owned
    fixture.close()
    assert not runtime.owned


def test_migration_environment_is_clean_and_uses_current_interpreter(runtime, fake_engine, monkeypatch):
    database = asyncio.run(runtime.create())
    monkeypatch.setenv("PGSERVICE", "untrusted")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("AURUM_AUTH_ENABLED", "true")
    calls = []
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    runtime.migrate(database, Path.cwd())
    args, options = calls[0]
    assert args[0] == [sys.executable, "-m", "alembic", "upgrade", "head"]
    environment = options["env"]
    assert environment["PATH"].split(":")[0] == str(Path(sys.executable).parent)
    assert set(environment) == {"PATH", "AURUM_POSTGRES_HOST", "AURUM_POSTGRES_PORT",
                                "AURUM_POSTGRES_USER", "AURUM_POSTGRES_PASSWORD", "AURUM_POSTGRES_DB"}
    assert environment["AURUM_POSTGRES_DB"] == database
    assert options["check"] is True


def test_migration_runner_uses_same_clean_environment(runtime, monkeypatch):
    from unit_tests import test_core_workspace_migration as migration

    database = "aurum_core_test_" + uuid4().hex
    monkeypatch.setitem(migration._owned_databases, database, (42, 7))
    monkeypatch.setenv("PGSERVICE", "untrusted")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    calls = []
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    migration._alembic(database, "upgrade", "head")
    args, options = calls[0]
    assert args[0] == [sys.executable, "-m", "alembic", "upgrade", "head"]
    assert "PGSERVICE" not in options["env"]
    assert "PYTHONPATH" not in options["env"]
