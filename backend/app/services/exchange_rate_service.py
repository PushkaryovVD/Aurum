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
