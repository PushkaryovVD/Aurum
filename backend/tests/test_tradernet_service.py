import hashlib
import hmac
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.tradernet_service import (
    TradernetUnavailable,
    fetch_portfolio,
    parse_portfolio,
    signed_headers,
)


def tradernet_settings() -> Settings:
    return Settings(
        tradernet_api_public_key="public-test-key",
        tradernet_api_secret_key=SecretStr("private-test-key"),
    )


def test_signing_uses_exact_body_and_timestamp_without_exposing_secret():
    settings = tradernet_settings()
    body = b'{"sample":"value"}'
    headers = signed_headers(settings, body, timestamp=1_700_000_000)
    expected = hmac.new(
        b"private-test-key", body + b"1700000000", hashlib.sha256
    ).hexdigest()
    assert headers == {
        "Content-Type": "application/json",
        "X-NtApi-PublicKey": "public-test-key",
        "X-NtApi-Sig": expected,
        "X-NtApi-Timestamp": "1700000000",
    }
    assert "private-test-key" not in json.dumps(headers)


def test_portfolio_parser_accepts_documented_response_and_keeps_decimal_precision():
    snapshot = parse_portfolio({
        "ps": {
            "acc": [{"curr": "USD", "s": "123.45000000", "currval": "1"}],
            "pos": [{
                "acc_pos_id": 85600002,
                "i": "AAPL.US",
                "q": "100.000000000001",
                "curr": "USD",
                "name2": "Apple Inc.",
                "mkt_price": "23.81000001",
                "market_value": "2381.000001",
                "bal_price_a": "29.924",
                "profit_price": "2.83",
            }],
        }
    })
    assert snapshot.accounts[0].available_funds.as_tuple().exponent == -8
    assert snapshot.positions[0].quantity.as_tuple().exponent == -12
    assert snapshot.positions[0].ticker == "AAPL.US"
    assert snapshot.positions[0].external_position_id == "85600002"


@pytest.mark.asyncio
async def test_fetch_portfolio_calls_only_read_only_position_command():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://tradernet.com/api/getPositionJson"
        assert request.content == b""
        assert request.headers["X-NtApi-PublicKey"] == "public-test-key"
        assert request.headers["X-NtApi-Sig"]
        return httpx.Response(200, json={"acc": [], "pos": []})

    snapshot = await fetch_portfolio(
        tradernet_settings(), transport=httpx.MockTransport(handler)
    )
    assert snapshot.accounts == []
    assert snapshot.positions == []


def test_portfolio_parser_rejects_error_and_malformed_rows():
    with pytest.raises(TradernetUnavailable):
        parse_portfolio({"error": "bad signature"})
    with pytest.raises(TradernetUnavailable):
        parse_portfolio({"acc": [], "pos": [{"i": "AAPL.US"}]})
