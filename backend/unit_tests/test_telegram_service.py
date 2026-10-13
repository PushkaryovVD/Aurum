from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from app.services.telegram_service import TelegramInitDataError, validate_init_data
from app.models.enums import TransactionType
from app.telegram_bot import parse_quick_transaction

TOKEN = "123456:test-token-used-only-in-unit-tests"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _signed_init_data(*, user_id: int = 42, auth_date: datetime = NOW) -> str:
    values = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAExample",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_init_data_returns_verified_user() -> None:
    user = validate_init_data(
        _signed_init_data(),
        bot_token=TOKEN,
        max_age=timedelta(minutes=5),
        now=NOW,
    )
    assert user["id"] == 42


def test_tampered_init_data_is_rejected() -> None:
    tampered = _signed_init_data().replace("%22id%22%3A42", "%22id%22%3A43")
    with pytest.raises(TelegramInitDataError, match="signature"):
        validate_init_data(tampered, bot_token=TOKEN, max_age=timedelta(minutes=5), now=NOW)


def test_expired_init_data_is_rejected() -> None:
    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_init_data(
            _signed_init_data(auth_date=NOW - timedelta(minutes=6)),
            bot_token=TOKEN,
            max_age=timedelta(minutes=5),
            now=NOW,
        )


@pytest.mark.parametrize(
    ("text", "kind", "amount", "description"),
    [
        ("-2500 кофе", TransactionType.EXPENSE, "2500.00", "кофе"),
        ("+500000 зарплата", TransactionType.INCOME, "500000.00", "зарплата"),
        ("-12,50 обед", TransactionType.EXPENSE, "12.50", "обед"),
    ],
)
def test_quick_transaction_parser(text, kind, amount, description) -> None:
    parsed = parse_quick_transaction(text)
    assert parsed is not None
    assert parsed == (kind, Decimal(amount), description)


@pytest.mark.parametrize("text", ["2500 кофе", "-0 кофе", "+12.345 кофе", "-2500"])
def test_quick_transaction_parser_rejects_ambiguous_input(text: str) -> None:
    assert parse_quick_transaction(text) is None
