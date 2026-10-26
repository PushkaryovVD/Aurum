"""Public auth readiness contract: no database, lifespan, or secrets."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_session
from app.api.routes.auth import router


class _ReadinessSession:
    def __init__(self, readiness: bool):
        self.readiness = readiness
        self.readiness_statement = None
        self.readiness_parameters = None

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def get(self, _model, _identifier):
        return None

    async def scalar(self, statement, _parameters=None):
        self.readiness_statement = statement
        self.readiness_parameters = _parameters
        return self.readiness


@pytest.mark.parametrize("required,ready,environment,allow_http,transport", [
    (False, True, "development", False, "https_or_loopback"),
    (True, True, "development", False, "https_or_loopback"),
    (True, False, "production", False, "https"),
    (True, False, "test", False, "https_or_loopback"),
    (True, True, "production", True, "http_or_https"),
])
@pytest.mark.asyncio
async def test_status_reports_database_backed_finance_readiness(required, ready, environment, allow_http, transport):
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        smtp_enabled=False,
        app_auth_required=required,
        environment=environment,
        allow_insecure_http=allow_http,
    )
    session = _ReadinessSession(ready)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "app_auth_required": required,
        "finance_access_ready": ready,
        "session_transport": transport,
        "initial_owner_bootstrap_required": required,
        "initial_owner_bootstrap_available": False,
        "password_reset_available": False,
    }


@pytest.mark.asyncio
async def test_required_auth_readiness_checks_workspace_identity_constraints_and_triggers():
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        smtp_enabled=False,
        app_auth_required=True,
        environment="development",
        allow_insecure_http=False,
    )
    session = _ReadinessSession(True)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/status")

    assert response.status_code == 200
    statement = session.readiness_statement
    assert statement is not None
    for identifier in (
        "alembic_version",
        "version_num",
    ):
        assert identifier in statement.text
    assert session.readiness_parameters == {"revision": "fa4d6e8b123"}


@pytest.mark.asyncio
async def test_initial_owner_endpoint_is_unavailable_when_application_auth_is_disabled():
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        smtp_enabled=False,
        app_auth_required=False,
        environment="development",
        allow_insecure_http=False,
    )

    async def override_get_session():
        yield _ReadinessSession(True)

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(router, prefix="/api")
    payload = {
        "bootstrap_code": "x" * 32,
        "identifier": "owner@example.com",
        "display_name": "Owner",
        "password": "correct horse battery staple",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/auth/bootstrap/initial-owner", json=payload, headers={"Origin": "https://test"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Initial owner setup is not available"}
