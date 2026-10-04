"""Actual default-fixture failure cleanup on the opted-in disposable cluster."""
import asyncio
import importlib.util
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from test_support.disposable_postgres import DisposablePostgres


def test_real_migration_failure_removes_exact_created_database(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("failed_migration_conftest", path)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    runtime = DisposablePostgres()
    created = []
    original_create = runtime.create
    original_run = subprocess.run

    async def tracked_create():
        database = await original_create()
        created.append(database)
        return database

    def invalid_revision(command, **options):
        assert command[-2:] == ["upgrade", "head"]
        # Exercise a real Alembic setup failure, not a fixture/plugin substitute.
        options.update(capture_output=True, text=True)
        return original_run(command[:-1] + ["missing_fixture_safety_revision"], **options)

    monkeypatch.setattr(runtime, "create", tracked_create)
    monkeypatch.setattr(harness, "DisposablePostgres", lambda: runtime)
    monkeypatch.setattr(subprocess, "run", invalid_revision)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        next(harness._test_database.__wrapped__())
    assert "missing_fixture_safety_revision" in failure.value.stdout + failure.value.stderr
    assert len(created) == 1
    assert not runtime.owned

    async def verify_absence():
        engine = create_async_engine(runtime.url("postgres"))
        try:
            async with engine.connect() as connection:
                await runtime.verify_cluster(connection)
                assert (await connection.execute(
                    text("SELECT oid FROM pg_database WHERE datname=:name"),
                    {"name": created[0]},
                )).scalar_one_or_none() is None
        finally:
            await engine.dispose()

    asyncio.run(verify_absence())
