"""Public auth readiness contract: no database, lifespan, or secrets."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.auth import router


@pytest.mark.parametrize("required,environment,transport", [
    (False, "development", "https_or_loopback"),
    (True, "development", "https_or_loopback"),
    (True, "production", "https"),
    (True, "test", "https_or_loopback"),
])
def test_status_is_public_nonsecret_and_never_finance_ready(required, environment, transport):
    app = FastAPI()
    app.state.settings = SimpleNamespace(app_auth_required=required, environment=environment)
    app.include_router(router, prefix="/api")
    response = TestClient(app).get("/api/auth/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "app_auth_required": required,
        "finance_access_ready": False,
        "session_transport": transport,
    }
