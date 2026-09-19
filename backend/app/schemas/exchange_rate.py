from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ExchangeRateRead(BaseModel):
    requested_date: date_
    effective_date: date_
    currency: str
    rate_to_kzt: Decimal
    source: str


class CrossRateRead(BaseModel):
    """One currency's price in another, resolved server-side.

    Rates are quoted against KZT, so a cross rate is the ratio of the two legs —
    arithmetic the transaction form used to do itself from two separate NBK
    lookups, where it could drift from what the reports compute.
    """

    requested_date: date_
    from_currency: str
    to_currency: str
    # How many units of `to_currency` one unit of `from_currency` buys.
    rate: Decimal
    # The KZT legs the ratio was built from, so a caller that also needs "what
    # is this currency worth in KZT" doesn't have to ask a second time.
    from_rate_to_kzt: Decimal
    to_rate_to_kzt: Decimal
    # The legs can come from different days: the loader walks back up to a week
    # when a currency had no quote on the requested day, and hiding that would
    # make the ratio look more precise than it is.
    from_effective_date: date_
    to_effective_date: date_


class ExchangeRateSync(BaseModel):
    start_date: date_
    end_date: date_
    currencies: list[str] = Field(min_length=1, max_length=40)

    @field_validator("currencies")
    @classmethod
    def _normalize_currencies(cls, value: list[str]) -> list[str]:
        normalized = [code.strip().upper() for code in value]
        if any(len(code) != 3 for code in normalized):
            raise ValueError("currency codes must be ISO 4217 three-letter codes")
        return list(dict.fromkeys(normalized))


class ExchangeRateSyncResult(BaseModel):
    synchronized: int
