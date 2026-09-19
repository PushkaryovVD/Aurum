from datetime import date as date_, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.exchange_rate import (
    CrossRateRead,
    ExchangeRateRead,
    ExchangeRateSync,
    ExchangeRateSyncResult,
)
from app.services.exchange_rate_service import cross_ratio, get_cross_rate, get_exchange_rate

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


def _to_read(row) -> ExchangeRateRead:
    return ExchangeRateRead(
        requested_date=row.requested_date,
        effective_date=row.effective_date,
        currency=row.currency,
        rate_to_kzt=row.rate_to_kzt,
        source=row.source,
    )


@router.get("", response_model=ExchangeRateRead)
async def read_exchange_rate(
    date: date_ = Query(), currency: str = Query(min_length=3, max_length=3), session: AsyncSession = Depends(get_session)
) -> ExchangeRateRead:
    row = await get_exchange_rate(session, date, currency)
    await session.commit()
    return _to_read(row)


@router.get("/cross", response_model=CrossRateRead)
async def read_cross_rate(
    date: date_ = Query(),
    from_currency: str = Query(alias="from", min_length=3, max_length=3),
    to_currency: str = Query(alias="to", min_length=3, max_length=3),
    session: AsyncSession = Depends(get_session),
) -> CrossRateRead:
    """One currency's price in another: `?from=USD&to=EUR` answers "how many
    euro does a dollar buy".

    Same currency on both sides is a legitimate question — the answer is 1 — and
    either side may be KZT. The response carries both KZT legs, so a caller that
    also needs "what is this currency worth in KZT" doesn't have to ask twice.
    """
    source, target = await get_cross_rate(session, date, from_currency, to_currency)
    await session.commit()
    return CrossRateRead(
        requested_date=date,
        from_currency=source.currency,
        to_currency=target.currency,
        rate=cross_ratio(source, target),
        from_rate_to_kzt=source.rate_to_kzt,
        to_rate_to_kzt=target.rate_to_kzt,
        from_effective_date=source.effective_date,
        to_effective_date=target.effective_date,
    )


@router.post("/sync", response_model=ExchangeRateSyncResult)
async def sync_exchange_rates(
    payload: ExchangeRateSync, session: AsyncSession = Depends(get_session)
) -> ExchangeRateSyncResult:
    if payload.end_date < payload.start_date or (payload.end_date - payload.start_date).days > 366:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="date range must be ordered and no longer than 366 days")
    count = 0
    day = payload.start_date
    while day <= payload.end_date:
        for currency in payload.currencies:
            await get_exchange_rate(session, day, currency)
            count += 1
        day += timedelta(days=1)
    await session.commit()
    return ExchangeRateSyncResult(synchronized=count)
