"""The cross-rate endpoint.

Every rate is seeded into the cache first, so no test ever reaches the real
National Bank service — `get_exchange_rate` returns a cached row without a
request, which is also the path the app takes in normal use.
"""
from datetime import date as date_, datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.exchange_rate import ExchangeRate

DAY = date_(2026, 9, 18)


async def _seed_rate(
    sessionmaker: async_sessionmaker[AsyncSession],
    currency: str,
    rate_to_kzt: str,
    *,
    requested_date: date_ = DAY,
    effective_date: date_ = DAY,
) -> None:
    async with sessionmaker() as session:
        session.add(
            ExchangeRate(
                requested_date=requested_date,
                effective_date=effective_date,
                currency=currency,
                rate_to_kzt=Decimal(rate_to_kzt),
                source="nbk",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _cross(client: AsyncClient, from_currency: str, to_currency: str):
    return await client.get(
        "/exchange-rates/cross",
        params={"date": DAY.isoformat(), "from": from_currency, "to": to_currency},
    )


async def test_cross_rate_divides_the_two_kzt_legs(client: AsyncClient, test_sessionmaker):
    await _seed_rate(test_sessionmaker, "USD", "500")
    await _seed_rate(test_sessionmaker, "EUR", "550")

    body = (await _cross(client, "USD", "EUR")).json()

    assert Decimal(body["rate"]) == Decimal("0.909091")
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "EUR"


async def test_cross_rate_against_kzt_is_the_leg_itself(client: AsyncClient, test_sessionmaker):
    await _seed_rate(test_sessionmaker, "USD", "500")

    body = (await _cross(client, "USD", "KZT")).json()

    assert Decimal(body["rate"]) == Decimal("500")


async def test_cross_rate_from_kzt_is_the_inverse(client: AsyncClient, test_sessionmaker):
    await _seed_rate(test_sessionmaker, "USD", "500")

    body = (await _cross(client, "KZT", "USD")).json()

    assert Decimal(body["rate"]) == Decimal("0.002")


async def test_the_same_currency_on_both_sides_is_one(client: AsyncClient, test_sessionmaker):
    await _seed_rate(test_sessionmaker, "USD", "500")

    body = (await _cross(client, "USD", "USD")).json()

    assert Decimal(body["rate"]) == Decimal("1")


async def test_the_response_reports_the_day_each_leg_came_from(client: AsyncClient, test_sessionmaker):
    """The legs need not share a date: the loader walks back up to a week when a
    currency had no quote on the requested day."""
    await _seed_rate(test_sessionmaker, "USD", "500", effective_date=DAY)
    await _seed_rate(test_sessionmaker, "EUR", "550", effective_date=date_(2026, 9, 15))

    body = (await _cross(client, "USD", "EUR")).json()

    assert body["requested_date"] == DAY.isoformat()
    assert body["from_effective_date"] == DAY.isoformat()
    assert body["to_effective_date"] == "2026-09-15"
    # Both legs travel with the ratio, so a caller that also wants "what is this
    # worth in KZT" doesn't have to ask a second time.
    assert Decimal(body["from_rate_to_kzt"]) == Decimal("500")
    assert Decimal(body["to_rate_to_kzt"]) == Decimal("550")


async def test_currency_codes_are_normalized(client: AsyncClient, test_sessionmaker):
    await _seed_rate(test_sessionmaker, "USD", "500")
    await _seed_rate(test_sessionmaker, "EUR", "550")

    body = (await _cross(client, "usd", "eur")).json()

    assert body["from_currency"] == "USD"
    assert Decimal(body["rate"]) == Decimal("0.909091")
