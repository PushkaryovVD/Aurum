from starlette.requests import Request

from app.api.deps import credential_transport_allowed, request_scheme
from app.core.config import Settings


PROXY_SECRET = "proxy-test-secret-with-at-least-32-bytes"


def _request(*, peer: str, headers: dict[str, str]) -> Request:
    raw_headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/bootstrap/initial-owner",
            "raw_path": b"/api/auth/bootstrap/initial-owner",
            "query_string": b"",
            "headers": raw_headers,
            "client": (peer, 12345),
            "server": ("backend", 8000),
        }
    )


def test_shared_proxy_identity_trusts_forwarded_loopback_from_dynamic_bridge_ip() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        app_auth_required=True,
        auth_hmac_secret="hmac-test-secret-with-at-least-32-bytes",
        auth_proxy_shared_secret=PROXY_SECRET,
        auth_trusted_proxy_cidrs="172.31.254.3/32",
        auth_loopback_client_cidrs="127.0.0.0/8,::1/128",
        auth_argon2_memory_kib=8192,
        auth_argon2_time_cost=2,
        auth_argon2_parallelism=1,
    )
    request = _request(
        peer="172.20.0.4",
        headers={
            "host": "localhost:3000",
            "x-aurum-proxy-token": PROXY_SECRET,
            "x-forwarded-proto": "http",
            "x-real-ip": "127.0.0.1",
        },
    )

    assert request_scheme(request, settings) == "http"
    assert credential_transport_allowed(request, settings) is True


def test_invalid_proxy_identity_cannot_assert_forwarded_https() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        app_auth_required=True,
        auth_hmac_secret="hmac-test-secret-with-at-least-32-bytes",
        auth_proxy_shared_secret=PROXY_SECRET,
    )
    request = _request(
        peer="172.20.0.4",
        headers={
            "host": "aurum.example",
            "x-aurum-proxy-token": "wrong-secret",
            "x-forwarded-proto": "https",
            "x-real-ip": "127.0.0.1",
        },
    )

    assert request_scheme(request, settings) == "http"
    assert credential_transport_allowed(request, settings) is False