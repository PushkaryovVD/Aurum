"""Shared test fixtures' plain-Python helpers (not pytest fixtures
themselves — those live in conftest.py)."""
from decimal import Decimal


def money(value) -> Decimal:
    """Compares amounts by value regardless of whether the API serializes
    Decimal as a JSON string or number — that's a wire-format detail, not
    business behavior worth pinning a test to."""
    return Decimal(str(value))


def txn_payload(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "10.00",
        "description": "test transaction",
        "date": "2026-01-15",
    }
    payload.update(overrides)
    return payload


async def pin_reporting_currency(client, headers: dict[str, str], currency: str = "KZT") -> None:
    """Give a workspace an explicit reporting currency.

    Workspaces a test inserts with raw SQL have no settings row, and the row
    the app would create for them defaults to USD — every aggregate would then
    be converted out of KZT (and need an exchange rate). Tests whose amounts
    are plain KZT ledger sums pin KZT first so they stay conversion-free."""
    response = await client.patch("/settings", json={"currency": currency}, headers=headers)
    assert response.status_code == 200, response.text
