"""Contracts for Telegram account linking and Mini App authentication."""
from pydantic import BaseModel, Field

from app.schemas.auth import AuthSessionResponse


class TelegramStatusResponse(BaseModel):
    configured: bool
    mini_app_configured: bool
    linked: bool
    username: str | None = None
    # Where bot quick entries and the Mini App land, so the user can see it.
    workspace_name: str | None = None
    account_name: str | None = None
    account_currency: str | None = None


class TelegramLinkCodeResponse(BaseModel):
    code: str
    expires_in_seconds: int


class TelegramMiniAppSessionRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=8192)


class TelegramMiniAppSessionResponse(AuthSessionResponse):
    pass
