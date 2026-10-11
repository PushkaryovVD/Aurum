"""Minimal read-only Tradernet API client.

The command surface is intentionally fixed to ``getPositionJson``. Keeping a
generic command proxy here would turn a display integration into an accidental
trading API as soon as a key with broader permissions was configured.
"""
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.investment import (
    TradernetAccountRead,
    TradernetPortfolioSnapshot,
    TradernetPositionRead,
)

TRADERNET_API_BASE_URL = "https://tradernet.com/api"


class TradernetUnavailable(RuntimeError):
    pass


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.tradernet_api_public_key.strip()
        and settings.tradernet_api_secret_key.get_secret_value().strip()
    )


def signed_headers(settings: Settings, body: bytes, timestamp: int | None = None) -> dict[str, str]:
    current = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(
        settings.tradernet_api_secret_key.get_secret_value().encode("utf-8"),
        body + current.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-NtApi-PublicKey": settings.tradernet_api_public_key,
        "X-NtApi-Sig": signature,
        "X-NtApi-Timestamp": current,
    }


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TradernetUnavailable("Tradernet returned an invalid numeric value") from exc


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TradernetUnavailable("Tradernet returned malformed portfolio data") from exc
    if not isinstance(value, dict):
        raise TradernetUnavailable("Tradernet returned an unexpected portfolio response")
    return value


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None and row.get(key) != "":
            return row[key]
    return None


def parse_portfolio(payload: Any) -> TradernetPortfolioSnapshot:
    root = _object(payload)
    if root.get("error") or root.get("errMsg"):
        raise TradernetUnavailable("Tradernet rejected the portfolio request")
    data = root.get("result", root)
    data = _object(data)
    data = _object(data.get("ps", data))
    accounts_raw, positions_raw = data.get("acc", []), data.get("pos", [])
    if not isinstance(accounts_raw, list) or not isinstance(positions_raw, list):
        raise TradernetUnavailable("Tradernet returned an unexpected portfolio response")

    accounts = []
    for row in accounts_raw:
        row = _object(row)
        currency = str(row.get("curr") or "").upper()
        available = _decimal(row.get("s"))
        if not currency or available is None:
            raise TradernetUnavailable("Tradernet returned an incomplete account balance")
        accounts.append(TradernetAccountRead(
            currency=currency,
            available_funds=available,
            exchange_rate=_decimal(row.get("currval")),
            forecast_in=_decimal(row.get("forecast_in")),
            forecast_out=_decimal(row.get("forecast_out")),
        ))

    positions = []
    for row in positions_raw:
        row = _object(row)
        ticker = str(row.get("i") or "").strip()
        currency = str(row.get("curr") or row.get("base_currency") or "").upper()
        quantity = _decimal(row.get("q"))
        if not ticker or not currency or quantity is None:
            raise TradernetUnavailable("Tradernet returned an incomplete position")
        external_id = row.get("acc_pos_id")
        positions.append(TradernetPositionRead(
            external_position_id=str(external_id) if external_id is not None else None,
            ticker=ticker,
            name=str(row.get("name2") or row.get("name") or ticker),
            currency=currency,
            quantity=quantity,
            market_price=_decimal(_first_present(row, "mkt_price", "close_price")),
            market_value=_decimal(row.get("market_value")),
            book_price=_decimal(_first_present(row, "bal_price_a", "price_a")),
            unrealized_profit=_decimal(row.get("profit_price")),
        ))
    return TradernetPortfolioSnapshot(
        fetched_at=datetime.now(UTC), accounts=accounts, positions=positions
    )


async def fetch_portfolio(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TradernetPortfolioSnapshot:
    if not is_configured(settings):
        raise TradernetUnavailable("Tradernet API is not configured")
    # The official client signs an empty body for a command with no data.
    # Signing ``{}`` instead produces a different digest and is rejected.
    body = b""
    url = f"{TRADERNET_API_BASE_URL}/getPositionJson"
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
        ) as client:
            response = await client.post(url, content=body, headers=signed_headers(settings, body))
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TradernetUnavailable("Tradernet portfolio is temporarily unavailable") from exc
    return parse_portfolio(payload)
