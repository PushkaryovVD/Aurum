"""Startup delivery contract for the first-owner operator capability."""

from fastapi import FastAPI

import app.main as main_module
from app.core.config import Settings


HMAC_SECRET = "lifespan-test-hmac-secret-with-at-least-32-bytes"


class _FakeSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        self.events.append("commit")


def _app(*, auth_required: bool) -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(
        _env_file=None,
        environment="development",
        app_auth_required=auth_required,
        auth_hmac_secret=HMAC_SECRET if auth_required else "",
    )
    return app


def _patch_startup_dependencies(monkeypatch, events: list[str]) -> None:
    monkeypatch.setattr(main_module, "AsyncSessionLocal", lambda: _FakeSession(events))

    async def seed(_session) -> None:
        events.append("seed")

    monkeypatch.setattr(main_module, "seed_default_categories", seed)
    monkeypatch.setattr(main_module, "seed_default_account", seed)
    monkeypatch.setattr(main_module, "seed_default_app_settings", seed)


async def test_lifespan_logs_raw_code_only_after_hmac_state_commit(monkeypatch) -> None:
    events: list[str] = []
    _patch_startup_dependencies(monkeypatch, events)

    async def issue(_session, **_kwargs) -> str:
        events.append("issue")
        return "operator-only-code"

    def warning(_message, *_args) -> None:
        events.append("warning")

    monkeypatch.setattr(main_module, "issue_initial_owner_bootstrap_code", issue)
    monkeypatch.setattr(main_module.logger, "warning", warning)

    async with main_module.lifespan(_app(auth_required=True)):
        pass

    assert events.index("issue") < events.index("commit") < events.index("warning")


async def test_lifespan_does_not_log_when_no_new_capability_is_issued(monkeypatch) -> None:
    events: list[str] = []
    _patch_startup_dependencies(monkeypatch, events)

    async def issue(_session, **_kwargs) -> None:
        events.append("issue")
        return None

    monkeypatch.setattr(main_module, "issue_initial_owner_bootstrap_code", issue)
    monkeypatch.setattr(main_module.logger, "warning", lambda *_args: events.append("warning"))

    async with main_module.lifespan(_app(auth_required=True)):
        pass

    assert "issue" in events
    assert "commit" in events
    assert "warning" not in events


async def test_lifespan_does_not_issue_or_log_when_auth_is_disabled(monkeypatch) -> None:
    events: list[str] = []
    _patch_startup_dependencies(monkeypatch, events)

    async def issue(_session, **_kwargs) -> None:
        events.append("issue")
        return None

    monkeypatch.setattr(main_module, "issue_initial_owner_bootstrap_code", issue)
    monkeypatch.setattr(main_module.logger, "warning", lambda *_args: events.append("warning"))

    async with main_module.lifespan(_app(auth_required=False)):
        pass

    assert "issue" not in events
    assert "commit" in events
    assert "warning" not in events
