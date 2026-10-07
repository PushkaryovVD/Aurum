"""API and negative tests for application session authentication."""
from collections.abc import AsyncGenerator
from http.cookies import SimpleCookie
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import Settings
from app.main import create_app
from app.models.auth import AuthRateLimit, SecurityAuditEvent, UserSession
from app.security.auth import PasswordService


HMAC_SECRET = "api-test-hmac-secret-with-at-least-32-bytes"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        app_auth_required=True,
        auth_hmac_secret=HMAC_SECRET,
        auth_argon2_memory_kib=8192,
        auth_argon2_time_cost=2,
        auth_argon2_parallelism=1,
        auth_login_max_attempts=2,
        auth_login_window_seconds=900,
        auth_login_block_seconds=900,
    )


@pytest_asyncio.fixture
async def auth_client(test_sessionmaker, auth_settings) -> AsyncGenerator[AsyncClient, None]:
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="https://test/api") as client:
        yield client


async def _bootstrap_user(
    test_sessionmaker,
    *,
    identifier: str = "owner@example.com",
    display_name: str = "Private owner",
    password: str = PASSWORD,
    status: str = "active",
) -> tuple[UUID, UUID, str]:
    user_id = uuid4()
    workspace_id = uuid4()
    old_password_service = PasswordService(memory_cost=8192, time_cost=1, parallelism=1)
    password_hash = old_password_service.hash(password)
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (id, normalized_login, display_name, status, password_hash)
                VALUES (:user_id, :identifier, :display_name, :status, :password_hash)
                """
            ),
            {
                "user_id": user_id,
                "identifier": identifier,
                "display_name": display_name,
                "status": status,
                "password_hash": password_hash,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO workspaces (id, kind, display_name, created_by_user_id, personal_owner_user_id)
                VALUES (:workspace_id, 'personal', 'Private workspace', :user_id, :user_id)
                """
            ),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
                VALUES (:membership_id, :workspace_id, :user_id, 'owner')
                """
            ),
            {"membership_id": uuid4(), "workspace_id": workspace_id, "user_id": user_id},
        )
        await session.execute(
            text("UPDATE users SET personal_workspace_id = :workspace_id WHERE id = :user_id"),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        await session.commit()
    return user_id, workspace_id, password_hash


def _session_token(response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie["aurum_session"].value


async def _login(client: AsyncClient, identifier: str = "owner@example.com", password: str = PASSWORD):
    return await client.post(
        "/auth/session",
        json={"identifier": identifier, "password": password},
        headers={"Origin": "https://test"},
    )


async def test_login_is_generic_rehashes_and_emits_only_secure_session_contract(
    auth_client, test_sessionmaker
):
    user_id, workspace_id, old_hash = await _bootstrap_user(test_sessionmaker)

    unknown = await _login(auth_client, "missing@example.com", "wrong")
    wrong = await _login(auth_client, password="wrong")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Unable to sign in"}

    response = await _login(auth_client, "  OWNER@EXAMPLE.COM  ")
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": str(user_id),
        "identifier": "owner@example.com",
        "display_name": "Private owner",
    }
    assert body["active_workspace"]["id"] == str(workspace_id)
    assert body["workspaces"] == [body["active_workspace"]]
    assert body["csrf_token"]
    assert PASSWORD not in response.text

    token = _session_token(response)
    assert token not in response.text
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie

    async with test_sessionmaker() as session:
        new_hash = (
            await session.execute(text("SELECT password_hash FROM users WHERE id = :id"), {"id": user_id})
        ).scalar_one()
        assert new_hash != old_hash
        assert PasswordService(memory_cost=8192, time_cost=2, parallelism=1).verify(new_hash, PASSWORD)
        stored = (await session.execute(select(UserSession))).scalar_one()
        assert token.encode() not in bytes(stored.token_hmac)
        assert body["csrf_token"].encode() not in bytes(stored.csrf_secret)


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b'{"identifier":1,"password":"wrong"}',
        b'{"identifier":"","password":"wrong"}',
        b'{"identifier":"owner\\ud800@example.com","password":"wrong"}',
        b'{"identifier":"owner@example.com","password":"wrong\\udfff"}',
        b'{"identifier":"owner@example.com","password":"wrong\\u0000password"}',
        b'{"identifier":"owner@example.com","password":"' + b"x" * 17000 + b'"}',
        b'{"identifier":' + b"1" * 5000 + b',"password":"wrong"}',
        '{"identifier":"owner@example.com","password":"correct horse battery staple"}'.encode(
            "utf-16"
        ),
        '{"identifier":"owner@example.com","password":"correct horse battery staple"}'.encode(
            "utf-32"
        ),
    ],
)
async def test_malformed_login_is_generic_audited_and_rate_limited(
    auth_client,
    test_sessionmaker,
    body,
):
    response = await auth_client.post(
        "/auth/session",
        content=body,
        headers={"Content-Type": "application/json", "Origin": "https://test"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Unable to sign in"}
    async with test_sessionmaker() as session:
        audit = (await session.execute(select(SecurityAuditEvent))).scalar_one()
        assert audit.event_type == "login"
        assert audit.outcome == "failure"
        limits = (await session.execute(select(AuthRateLimit))).scalars().all()
        assert len(limits) == 3


async def test_login_rejects_cross_origin_and_non_json_requests_before_authentication(
    auth_client,
    test_sessionmaker,
):
    await _bootstrap_user(test_sessionmaker)
    payload = '{"identifier":"owner@example.com","password":"correct horse battery staple"}'
    cross_origin = await auth_client.post(
        "/auth/session",
        content=payload,
        headers={"Content-Type": "text/plain", "Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 404
    auth_client.cookies.clear()
    wrong_media_type = await auth_client.post(
        "/auth/session",
        content=payload,
        headers={"Content-Type": "text/plain", "Origin": "https://test"},
    )
    assert wrong_media_type.status_code == 401
    assert "aurum_session" not in auth_client.cookies


async def test_chunked_login_body_stops_at_streaming_limit(auth_client, test_sessionmaker):
    async def oversized_body():
        yield b'{"identifier":"owner@example.com","password":"'
        yield b"x" * 9000
        yield b"x" * 9000
        yield b'"}'

    response = await auth_client.post(
        "/auth/session",
        content=oversized_body(),
        headers={"Content-Type": "application/json", "Origin": "https://test"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Unable to sign in"}
    async with test_sessionmaker() as session:
        assert (await session.execute(select(SecurityAuditEvent))).scalar_one().outcome == "failure"


async def test_required_auth_gates_routes_and_enforces_csrf(auth_client, test_sessionmaker):
    await _bootstrap_user(test_sessionmaker)

    assert (await auth_client.get("/health")).status_code == 200
    assert (await auth_client.get("/accounts")).status_code == 503
    assert (await auth_client.get("/docs")).status_code == 404
    assert (await auth_client.get("/redoc")).status_code == 404
    assert (await auth_client.get("/openapi.json")).status_code == 404

    login = await _login(auth_client)
    csrf_token = login.json()["csrf_token"]
    assert (await auth_client.get("/accounts")).status_code == 503

    payload = {"name": "Cash", "type": "cash", "currency": "KZT"}
    assert (await auth_client.post("/accounts", json=payload)).status_code == 503
    assert (
        await auth_client.post(
            "/accounts",
            json=payload,
            headers={"X-CSRF-Token": csrf_token, "Origin": "https://evil.example"},
        )
    ).status_code == 503
    created = await auth_client.post(
        "/accounts",
        json=payload,
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://test"},
    )
    assert created.status_code == 503


async def test_login_rejects_spoofed_loopback_host_over_remote_http(test_sessionmaker, auth_settings):
    await _bootstrap_user(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("203.0.113.10", 12345))
    async with AsyncClient(transport=transport, base_url="http://localhost/api") as client:
        response = await client.post(
            "/auth/session",
            json={"identifier": "owner@example.com", "password": PASSWORD},
            headers={"X-Forwarded-Proto": "https", "X-Real-IP": "127.0.0.1"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Authentication is not available"}


async def test_login_accepts_https_marker_only_from_trusted_internal_proxy(
    test_sessionmaker, auth_settings
):
    await _bootstrap_user(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("172.31.254.3", 12345))
    async with AsyncClient(transport=transport, base_url="http://aurum.local/api") as client:
        response = await client.post(
            "/auth/session",
            json={"identifier": "owner@example.com", "password": PASSWORD},
            headers={
                "Origin": "https://aurum.local",
                "X-Forwarded-Proto": "https",
                "X-Real-IP": "192.168.1.10",
            },
        )

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


async def test_trusted_tls_proxy_preserves_distinct_client_rate_limit_buckets(
    test_sessionmaker, auth_settings
):
    await _bootstrap_user(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("172.31.254.3", 12345))
    async with AsyncClient(transport=transport, base_url="http://aurum.local/api") as client:
        first_headers = {
            "Origin": "https://aurum.local",
            "X-Forwarded-Proto": "https",
            "X-Real-IP": "198.51.100.10",
        }
        second_headers = {
            "Origin": "https://aurum.local",
            "X-Forwarded-Proto": "https",
            "X-Real-IP": "198.51.100.11",
        }
        for attempt in range(8):
            payload = {"identifier": f"missing-{attempt}@example.com", "password": "wrong-password"}
            assert (
                await client.post("/auth/session", json=payload, headers=first_headers)
            ).status_code == 401
        blocked_payload = {"identifier": "blocked@example.com", "password": "wrong-password"}
        assert (
            await client.post("/auth/session", json=blocked_payload, headers=first_headers)
        ).status_code == 429
        assert (
            await client.post("/auth/session", json=blocked_payload, headers=second_headers)
        ).status_code == 401


async def test_login_rejects_forwarded_headers_from_untrusted_sibling_container(
    test_sessionmaker, auth_settings
):
    await _bootstrap_user(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("172.20.0.10", 12345))
    async with AsyncClient(transport=transport, base_url="http://localhost/api") as client:
        response = await client.post(
            "/auth/session",
            json={"identifier": "owner@example.com", "password": PASSWORD},
            headers={"X-Forwarded-Proto": "https", "X-Real-IP": "127.0.0.1"},
        )

    assert response.status_code == 404


async def test_login_allows_default_nginx_chain_only_for_host_loopback_client(
    test_sessionmaker, auth_settings
):
    await _bootstrap_user(test_sessionmaker)
    auth_app = create_app(auth_settings)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    auth_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=auth_app, client=("172.31.254.3", 12345))
    async with AsyncClient(transport=transport, base_url="http://localhost:3000/api") as client:
        local = await client.post(
            "/auth/session",
            json={"identifier": "owner@example.com", "password": PASSWORD},
            headers={
                "Origin": "http://localhost:3000",
                "X-Forwarded-Proto": "http",
                "X-Real-IP": "172.31.254.1",
            },
        )
        lan = await client.post(
            "/auth/session",
            json={"identifier": "owner@example.com", "password": PASSWORD},
            headers={
                "Origin": "http://localhost:3000",
                "X-Forwarded-Proto": "http",
                "X-Real-IP": "192.168.1.10",
            },
        )
        logout = await client.delete(
            "/auth/session",
            headers={
                "Origin": "http://localhost:3000",
                "X-CSRF-Token": local.json()["csrf_token"],
                "X-Forwarded-Proto": "http",
                "X-Real-IP": "172.31.254.1",
            },
        )

    assert local.status_code == 200
    assert lan.status_code == 404
    assert logout.status_code == 204


async def test_me_selects_only_accessible_workspace_and_reissues_csrf(auth_client, test_sessionmaker):
    _user_id, workspace_id, _password_hash = await _bootstrap_user(test_sessionmaker)
    login = await _login(auth_client)
    login_body = login.json()

    me = await auth_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json() == login_body

    selected = await auth_client.get(
        "/auth/me",
        headers={"X-Aurum-Workspace": str(workspace_id)},
    )
    assert selected.status_code == 200
    assert selected.json()["active_workspace"]["id"] == str(workspace_id)
    assert (
        await auth_client.get("/auth/me", headers={"X-Aurum-Workspace": str(uuid4())})
    ).status_code == 404
    assert (
        await auth_client.get("/auth/me", headers={"X-Aurum-Workspace": "not-a-uuid"})
    ).status_code == 404


async def test_login_rotates_and_logout_requires_csrf_then_revokes(auth_client, test_sessionmaker):
    await _bootstrap_user(test_sessionmaker)
    first = await _login(auth_client)
    first_token = _session_token(first)
    second = await _login(auth_client)
    second_token = _session_token(second)
    csrf_token = second.json()["csrf_token"]
    assert second_token != first_token

    auth_client.cookies.clear()
    auth_client.cookies.set("aurum_session", first_token)
    assert (await auth_client.get("/auth/me")).status_code == 401
    auth_client.cookies.clear()
    auth_client.cookies.set("aurum_session", second_token)

    assert (await auth_client.delete("/auth/session")).status_code == 403
    logout = await auth_client.delete(
        "/auth/session",
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://test"},
    )
    assert logout.status_code == 204
    assert "max-age=0" in logout.headers["set-cookie"].lower()
    assert (await auth_client.get("/auth/me")).status_code == 401

    async with test_sessionmaker() as session:
        records = (await session.execute(select(UserSession).order_by(UserSession.created_at))).scalars().all()
        assert len(records) == 2
        assert all(record.revoked_at is not None for record in records)


async def test_disabled_user_and_rate_limit_are_non_disclosing(auth_client, test_sessionmaker):
    await _bootstrap_user(test_sessionmaker, status="disabled")

    first = await _login(auth_client)
    second = await _login(auth_client)
    blocked = await _login(auth_client)
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json() == {"detail": "Unable to sign in"}
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Unable to sign in"}

    async with test_sessionmaker() as session:
        rate_records = (await session.execute(select(AuthRateLimit))).scalars().all()
        assert len(rate_records) == 3
        assert sorted(record.attempt_count for record in rate_records) == [2, 2, 2]
        assert all(b"owner@example.com" not in bytes(record.bucket_hmac) for record in rate_records)
