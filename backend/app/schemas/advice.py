from typing import Literal

from pydantic import BaseModel


class AdviceItem(BaseModel):
    key: str
    tone: Literal["positive", "neutral", "warning"]
    # Frontend-translated by key — same key+params pattern as FinancialAlert,
    # extended to allow string params (category names) alongside numbers.
    params: dict[str, str | int | float]


class AdviceResponse(BaseModel):
    # The currency of every money param (amount/current/average) in `items`.
    reporting_currency: str
    # True when some month's totals could not be converted (no rate); advice
    # that would have needed them is left out rather than guessed.
    incomplete: bool = False
    items: list[AdviceItem]
