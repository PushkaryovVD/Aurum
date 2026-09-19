"""Historical official-rate loading from the National Bank of Kazakhstan."""
from datetime import date as date_, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_rate import ExchangeRate

NBK_RATES_URL = "https://nationalbank.kz/rss/get_rates.cfm"
MAX_PREVIOUS_DAYS = 7


def _text(element: ElementTree.Element, name: str) -> str | None:
    for child in element:
        if child.tag.rsplit("}", 1)[-1].lower() == name:
            return child.text.strip() if child.text else None
    return None


def _parse_rate(xml: bytes, currency: str) -> Decimal | None:
    root = ElementTree.fromstring(xml)
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1].lower() != "item":
            continue
        code = _text(item, "title") or _text(item, "currency")
        if code and code.upper() == currency:
            raw_rate = _text(item, "description") or _text(item, "rate")
            raw_quantity = _text(item, "quant") or _text(item, "quantity") or "1"
            if raw_rate is None:
                return None
            try:
                rate = Decimal(raw_rate.replace(" ", "").replace(",", "."))
                quantity = Decimal(raw_quantity.replace(" ", "").replace(",", "."))
            except InvalidOperation:
                return None
            return rate / quantity if quantity else None
    return None


async def get_exchange_rate(
    session: AsyncSession, requested_date: date_, currency: str, *, force: bool = False, timeout: float = 10.0
) -> ExchangeRate:
    currency = currency.upper()
    if currency == "KZT":
        return ExchangeRate(
            requested_date=requested_date,
            effective_date=requested_date,
            currency="KZT",
            rate_to_kzt=Decimal("1"),
            source="identity",
            fetched_at=datetime.now(timezone.utc),
        )

    existing = (
        await session.execute(
            select(ExchangeRate).where(
                ExchangeRate.requested_date == requested_date,
                ExchangeRate.currency == currency,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and not force:
        return existing

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for offset in range(MAX_PREVIOUS_DAYS + 1):
                effective_date = requested_date - timedelta(days=offset)
                response = await client.get(
                    NBK_RATES_URL,
                    params={"fdate": effective_date.strftime("%d.%m.%Y")},
                )
                response.raise_for_status()
                rate = _parse_rate(response.content, currency)
                if rate is None:
                    continue
                row = existing or ExchangeRate(requested_date=requested_date, currency=currency)
                row.effective_date = effective_date
                row.rate_to_kzt = rate
                row.source = "nbk"
                row.fetched_at = datetime.now(timezone.utc)
                session.add(row)
                await session.flush()
                return row
    except (httpx.HTTPError, ElementTree.ParseError) as exc:
        raise HTTPException(status_code=503, detail="NBK exchange-rate service is unavailable") from exc

    raise HTTPException(status_code=422, detail=f"No NBK rate found for {currency} near {requested_date.isoformat()}")


# A cross rate is a ratio of two KZT quotes; six places is the precision the
# transaction form stores its rate at.
CROSS_RATE_PRECISION = Decimal("0.000001")


async def get_cross_rate(
    session: AsyncSession, requested_date: date_, from_currency: str, to_currency: str
) -> tuple[ExchangeRate, ExchangeRate]:
    """The two KZT legs whose ratio is the cross rate.

    Returns both rows rather than a bare number so the caller can see which days
    the ratio was actually built from — the legs are not guaranteed to share one.
    """
    source = await get_exchange_rate(session, requested_date, from_currency)
    target = await get_exchange_rate(session, requested_date, to_currency)
    return source, target


def cross_ratio(source: ExchangeRate, target: ExchangeRate) -> Decimal:
    """How many units of `target` one unit of `source` buys.

    Both sides may be KZT: `get_exchange_rate` answers that with an identity row
    worth 1, so KZT→USD and USD→KZT fall out of the same division.
    """
    if not target.rate_to_kzt:
        raise HTTPException(status_code=422, detail=f"No usable KZT rate for {target.currency}")
    return (source.rate_to_kzt / target.rate_to_kzt).quantize(CROSS_RATE_PRECISION)
