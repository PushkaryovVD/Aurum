"""Public auth readiness contract: no database, lifespan, or secrets."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_session
from app.api.routes.auth import router


class _EmptyBootstrapSession:
    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def get(self, _model, _identifier):
        return None


@pytest.mark.parametrize("required,environment,transport", [
    (False, "development", "https_or_loopback"),
    (True, "development", "https_or_loopback"),
    (True, "production", "https"),
    (True, "test", "https_or_loopback"),
])
@pytest.mark.asyncio
async def test_status_reports_legacy_finance_ready_only_when_auth_is_disabled(required, environment, transport):
    app = FastAPI()
    app.state.settings = SimpleNamespace(app_auth_required=required, environment=environment)

    async def override_get_session():
        yield _EmptyBootstrapSession()

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "app_auth_required": required,
        "finance_access_ready": not required,
        "session_transport": transport,
        "initial_owner_bootstrap_required": required,
        "initial_owner_bootstrap_available": False,
    }


@pytest.mark.asyncio
async def test_initial_owner_endpoint_is_unavailable_when_application_auth_is_disabled():
    app = FastAPI()
    app.state.settings = SimpleNamespace(app_auth_required=False, environment="development")

    async def override_get_session():
        yield _EmptyBootstrapSession()

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
