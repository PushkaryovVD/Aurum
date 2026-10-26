"""Application configuration, sourced from environment variables (.env)."""
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the running app's version — surfaced in the API
# title, in GET /api/settings as app_version (which the frontend reads to show
# it in Settings; it deliberately does NOT ride on the unauthenticated
# /api/health), and embedded in exported backups so an old file can be told
# apart from a current one.
APP_VERSION = "1.1.8"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AURUM_", extra="ignore")

    # Postgres connection
    postgres_user: str = "aurum"
    postgres_password: str = "aurum"
    postgres_db: str = "aurum"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Default currency shown across the UI when an account doesn't override it
    default_currency: str = "KZT"

    # Comma-separated list of browser origins allowed to call the API. Empty
    # by default, which allows none: the shipped compose serves the UI and the
    # API from one nginx, and the Vite dev server proxies /api, so neither is
    # a cross-origin caller. Set it only for a genuinely separate frontend.
    cors_origins: str = ""

    # CoinGecko Demo API key (free, no card required — https://www.coingecko.com/en/api/pricing)
    # for services/crypto_service.py's price lookups. Empty by default; the
    # Crypto tab's endpoints 400 with a clear message until this is set,
    # rather than silently hitting CoinGecko's much stingier keyless tier.
    coingecko_api_key: str = ""

    # Read-only Tradernet integration. Generate a dedicated API key without
    # trading permission and keep both values in the deployment environment.
    tradernet_api_public_key: str = ""
    tradernet_api_secret_key: SecretStr = SecretStr("")

    # Telegram bot / Mini App integration. The token is intentionally a
    # SecretStr so accidental settings dumps cannot reveal it. The public URL
    # must be HTTPS because Telegram opens Mini Apps only from secure origins.
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webapp_url: str = ""
    telegram_init_data_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    telegram_link_code_ttl_seconds: int = Field(default=600, ge=60, le=3600)

    # Outgoing mail for invitations (optional). With Gmail use smtp.gmail.com,
    # port 587 (STARTTLS) and an app password, never the account password.
    # The password is a SecretStr and lives only in the private .env file.
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    # Sender address; defaults to smtp_username when blank.
    smtp_from: str = ""
    # "starttls" (port 587), "ssl" (port 465) or "none" (trusted relay only).
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = Field(default=15, gt=0, le=120)
    # Public address used in invitation links, e.g. http://192.168.1.16:3000.
    # Blank means "the address the inviter is using right now".
    public_url: str = ""

    # Swagger/ReDoc/openapi.json opt-in for legacy auth-disabled mode. The
    # docs_enabled property below always suppresses them when application auth
    # is required, regardless of this compatibility default.
    enable_docs: bool = True

    # Authentication remains opt-in so this bounded slice cannot unexpectedly
    # lock an existing installation out of its data.
    app_auth_required: bool = False
    # Self-hosted installations commonly terminate TLS at Cloudflare, a NAS
    # gateway, or not at all on a trusted LAN. Keep the transport policy
    # explicit instead of inferring it from the deployment environment.
    # Plain HTTP is allowed by default (matching docker-compose.yml); set
    # AURUM_ALLOW_INSECURE_HTTP=false for an HTTPS-only deployment.
    allow_insecure_http: bool = True

    environment: Literal["development", "test", "production"] = "development"
    auth_hmac_secret: SecretStr = SecretStr("")
    # Compose provisions this installation-owned file automatically in a
    # private named volume. It lets first-owner setup work without asking an
    # operator to edit an environment file, while keeping the key outside the
    # database and application logs.
    auth_hmac_secret_file: str = ""
    # Shared only with the shipped nginx container. Unlike a bridge address,
    # this identity survives CasaOS/Compose network rewriting while still
    # preventing arbitrary sibling containers from asserting forwarded data.
    auth_proxy_shared_secret: SecretStr = SecretStr("")
    auth_proxy_shared_secret_file: str = ""
    # The shipped nginx authenticates itself with a generated shared secret.
    # CIDR trust stays available for custom deployments but is empty by
    # default so Docker can allocate any non-conflicting bridge subnet.
    auth_trusted_proxy_cidrs: str = ""
    auth_loopback_client_cidrs: str = "127.0.0.0/8,::1/128"
    auth_session_idle_seconds: int = Field(default=1800, ge=60, le=86400)
    auth_session_absolute_seconds: int = Field(default=604800, ge=300, le=2592000)
    auth_argon2_memory_kib: int = Field(default=65536, ge=8192, le=1048576)
    auth_argon2_time_cost: int = Field(default=3, ge=1, le=10)
    auth_argon2_parallelism: int = Field(default=4, ge=1, le=16)
    auth_argon2_hash_length: int = Field(default=32, ge=16, le=64)
    auth_argon2_salt_length: int = Field(default=16, ge=16, le=64)
    auth_login_max_attempts: int = Field(default=5, ge=1, le=100)
    auth_login_window_seconds: int = Field(default=900, ge=60, le=86400)
    auth_login_block_seconds: int = Field(default=900, ge=60, le=86400)
    auth_invitation_max_attempts: int = Field(default=10, ge=1, le=100)
    auth_invitation_window_seconds: int = Field(default=900, ge=60, le=86400)
    auth_invitation_block_seconds: int = Field(default=900, ge=60, le=86400)
    initial_owner_bootstrap_ttl_seconds: int = Field(default=900, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_auth_security(self) -> "Settings":
        if not self.auth_hmac_secret.get_secret_value() and self.auth_hmac_secret_file:
            try:
                secret = Path(self.auth_hmac_secret_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError("authentication HMAC secret file is unavailable") from exc
            self.auth_hmac_secret = SecretStr(secret)
        if (
            not self.auth_proxy_shared_secret.get_secret_value()
            and self.auth_proxy_shared_secret_file
        ):
            try:
                proxy_secret = Path(self.auth_proxy_shared_secret_file).read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise ValueError("authentication proxy identity file is unavailable") from exc
            self.auth_proxy_shared_secret = SecretStr(proxy_secret)
        if self.auth_session_idle_seconds > self.auth_session_absolute_seconds:
            raise ValueError("session idle lifetime must not exceed absolute lifetime")

        if not self.app_auth_required:
            return self

        secret = self.auth_hmac_secret.get_secret_value()
        default_like = {
            "change-me",
            "changeme",
            "default",
            "replace-me",
            "replace-me-with-a-secret",
            "secret",
        }
        if len(secret.encode("utf-8")) < 32 or secret.strip().casefold() in default_like:
            raise ValueError("authentication HMAC secret must be at least 32 bytes and non-default")
        proxy_secret = self.auth_proxy_shared_secret.get_secret_value()
        if proxy_secret and len(proxy_secret.encode("utf-8")) < 32:
            raise ValueError("authentication proxy identity must be at least 32 bytes")

        if self.environment != "development" and (
            self.auth_argon2_memory_kib < 19456 or self.auth_argon2_time_cost < 2
        ):
            raise ValueError("Argon2 parameters are too weak for non-development authentication")
        return self

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def auth_trusted_proxy_cidrs_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.auth_trusted_proxy_cidrs.split(",") if cidr.strip()]

    @property
    def auth_loopback_client_cidrs_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.auth_loopback_client_cidrs.split(",") if cidr.strip()]

    @property
    def auth_session_idle_lifetime(self) -> timedelta:
        return timedelta(seconds=self.auth_session_idle_seconds)

    @property
    def auth_session_absolute_lifetime(self) -> timedelta:
        return timedelta(seconds=self.auth_session_absolute_seconds)

    @property
    def docs_enabled(self) -> bool:
        """Keep API metadata unavailable whenever application auth is enabled."""
        return self.enable_docs and not self.app_auth_required

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host.strip() and (self.smtp_from.strip() or self.smtp_username.strip()))

    @property
    def smtp_sender(self) -> str:
        return self.smtp_from.strip() or self.smtp_username.strip()

    @property
    def telegram_mini_app_enabled(self) -> bool:
        """Invalid/incomplete Mini App config must not disable bot-only mode."""
        token = self.telegram_bot_token.get_secret_value()
        url = self.telegram_webapp_url.strip()
        parsed = urlsplit(url)
        return bool(token and parsed.scheme == "https" and parsed.hostname)


@lru_cache
def get_settings() -> Settings:
    return Settings()
