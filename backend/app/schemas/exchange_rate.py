from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ExchangeRateRead(BaseModel):
    requested_date: date_
    effective_date: date_
    currency: str
    rate_to_kzt: Decimal
    source: str


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
