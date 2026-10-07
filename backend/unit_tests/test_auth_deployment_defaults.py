"""Deployment defaults for the first-owner test rollout."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_develop_compose_enables_first_owner_setup_without_operator_env_edits() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AURUM_APP_AUTH_REQUIRED: ${AURUM_APP_AUTH_REQUIRED:-true}" in compose
    assert "AURUM_APP_AUTH_REQUIRED=true" in env_example


def test_disposable_postgres_runtime_is_never_a_deployment_setting() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AURUM_DISPOSABLE_POSTGRES_RUNTIME" not in compose
    assert "AURUM_DISPOSABLE_POSTGRES_RUNTIME" not in env_example


def test_tls_proxy_uses_an_internal_port_instead_of_trusting_client_forwarded_proto() -> None:
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    tls_compose = (ROOT / "docker-compose.tls.yml").read_text(encoding="utf-8")

    assert "$http_x_forwarded_proto" not in nginx
    assert "listen 8080;" in nginx
    assert '"8080:172.31.255.2" 1;' in nginx
    assert "reverse_proxy web:8080" in caddy
    assert "header_up X-Real-IP {remote_host}" in caddy
    assert "8080 $http_x_real_ip;" in nginx
    assert "default $remote_addr;" in nginx
    assert "limit_req_zone $aurum_forwarded_client" in nginx
    assert "proxy_set_header X-Real-IP $aurum_forwarded_client;" in nginx
    assert (
        "auth/bootstrap/initial-owner|auth/invitations/accept|workspaces/invitations/accept|"
        "workspaces/[^/]+/invitations"
    ) in nginx
    assert "client_max_body_size 16k;" in nginx
    assert "subnet: 172.31.255.0/29" in tls_compose
    assert "ipv4_address: 172.31.255.2" in tls_compose
    assert "ipv4_address: 172.31.255.3" in tls_compose


def test_nginx_preserves_external_host_port_for_same_origin_checks() -> None:
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")

    assert "default $http_host;" in nginx
    assert "proxy_set_header Host $aurum_forwarded_host;" in nginx
    assert "proxy_set_header Host $host;" not in nginx


def test_compose_binds_nginx_to_the_backend_trusted_proxy_identity() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "subnet: 172.31.254.0/29" in compose
    assert "gateway: 172.31.254.1" in compose
    assert "ipv4_address: 172.31.254.3" in compose
    assert "AURUM_AUTH_TRUSTED_PROXY_CIDRS: 172.31.254.3/32" in compose
    assert "AURUM_AUTH_LOOPBACK_CLIENT_CIDRS: 127.0.0.0/8,::1/128,172.31.254.1/32" in compose


def test_operator_guidance_matches_default_required_auth_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "DOCS.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = (
        ROOT / "frontend/docker-entrypoint.d/20-basic-auth.sh"
    ).read_text(encoding="utf-8")

    combined = "\n".join((readme, docs, env_example, compose, entrypoint))
    assert "has no built-in login system" not in combined
    assert "This instance has NO authentication" not in combined
    assert "Both unset = no login screen at all" not in combined
    assert "default required-auth" in readme
    assert "readiness-blocked with `503`" in docs
    assert "Required application authentication always suppresses" in env_example
    assert "Basic Auth perimeter is disabled" in entrypoint
