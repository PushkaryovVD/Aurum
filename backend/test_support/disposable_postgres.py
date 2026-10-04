"""Test-only PostgreSQL lifecycle. Never derives endpoints from app settings."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine


class DisposablePostgres:
    """One explicitly opted-in cluster and exact process-owned database identities."""

    def __init__(self, prefix="aurum_fixture_test_", owned=None):
        if prefix not in ("aurum_fixture_test_", "aurum_core_test_"):
            raise ValueError("unsupported disposable database namespace")
        self.prefix = prefix
        runtime_path = os.environ.get("AURUM_DISPOSABLE_POSTGRES_RUNTIME")
        if not runtime_path:
            raise ValueError("explicit disposable PostgreSQL runtime metadata is required")
        path = Path(runtime_path).resolve()
        runtime = json.loads(path.read_text())
        self.host = os.environ.get("AURUM_POSTGRES_HOST")
        self.port = int(os.environ.get("AURUM_POSTGRES_PORT", "0"))
        self.user = os.environ.get("AURUM_POSTGRES_USER")
        self.password = os.environ.get("AURUM_POSTGRES_PASSWORD")
        self.data = Path(runtime["data"]).resolve()
        workspace = Path(runtime["workspace"]).resolve()
        if (runtime.get("disposable") is not True or self.host != "127.0.0.1" or
            (self.host, self.port, self.user) !=
            (runtime.get("host"), runtime.get("port"), runtime.get("user")) or
            not 1 <= self.port <= 65535 or not self.user or self.password is None or
            path.parent != workspace or self.data.parent != workspace or
            not (self.data / "PG_VERSION").is_file()):
            raise ValueError("runtime is not the explicitly provisioned owned loopback cluster")
        self.owned: dict[str, tuple[int, int]] = owned if owned is not None else {}

    def url(self, database):
        if database != "postgres" and database not in self.owned:
            raise ValueError("database is not owned by this test process")
        return URL.create("postgresql+asyncpg", username=self.user, password=self.password,
                          host=self.host, port=self.port, database=database)

    async def verify_cluster(self, connection):
        actual = (await connection.execute(text("SHOW data_directory"))).scalar_one()
        if Path(actual).resolve() != self.data:
            raise ValueError("connected cluster does not match owned runtime data directory")
        user = (await connection.execute(text("SELECT current_user"))).scalar_one()
        if user != self.user:
            raise ValueError("connected role does not match owned runtime user")

    async def identity(self, connection, database):
        return (await connection.execute(text(
            "SELECT oid, datdba FROM pg_database WHERE datname=:name AND "
            "datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)"
        ), {"name": database})).one_or_none()

    async def create(self, database=None):
        database = database or self.prefix + uuid4().hex
        if not re.fullmatch(re.escape(self.prefix) + r"[0-9a-f]{32}", database):
            raise ValueError("only uniquely named owned fixture databases are allowed")
        engine = create_async_engine(self.url("postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await self.verify_cluster(connection)
                # CREATE-only: a collision must fail, never drop preexisting data.
                await connection.execute(text(f'CREATE DATABASE "{database}"'))
                identity = await self.identity(connection, database)
                if identity is None:
                    raise ValueError("created database ownership could not be verified")
                self.owned[database] = tuple(identity)
            return database
        finally:
            await engine.dispose()

    async def drop(self, database):
        if database not in self.owned:
            raise ValueError("refusing to drop a database not created by this test process")
        engine = create_async_engine(self.url("postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await self.verify_cluster(connection)
                identity = await self.identity(connection, database)
                if identity is None or tuple(identity) != self.owned[database]:
                    raise ValueError("refusing to drop a replaced or unowned database")
                # No FORCE: leaked connections fail cleanup rather than terminate
                # another process. All fixture engines must be disposed first.
                await connection.execute(text(f'DROP DATABASE "{database}"'))
                remaining = (await connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
                )).scalar_one_or_none()
                if remaining is not None:
                    raise ValueError("owned database cleanup could not be verified")
                del self.owned[database]
        finally:
            await engine.dispose()

    def alembic(self, database, backend_dir, *arguments, check=True, capture_output=False):
        # Never migrate an unowned target, including the administrative database.
        if database not in self.owned:
            raise ValueError("database is not owned by this test process")
        # Do not inherit application configuration, PG* overrides, or Python hooks.
        bin_dir = str(Path(sys.executable).parent)
        environment = {
            "PATH": bin_dir + os.pathsep + os.defpath,
            "AURUM_POSTGRES_HOST": self.host,
            "AURUM_POSTGRES_PORT": str(self.port),
            "AURUM_POSTGRES_USER": self.user,
            "AURUM_POSTGRES_PASSWORD": self.password,
            "AURUM_POSTGRES_DB": database,
        }
        return subprocess.run([sys.executable, "-m", "alembic", *arguments],
                              cwd=backend_dir, env=environment, check=check,
                              capture_output=capture_output, text=True)

    def migrate(self, database, backend_dir):
        return self.alembic(database, backend_dir, "upgrade", "head")
