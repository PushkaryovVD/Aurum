from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel


class CashFlowPoint(BaseModel):
    year: int
    month: int
    # In CashFlowResponse.reporting_currency, at the official rate for the
    # month's last day. None when that month had money but no rate.
    income: Decimal | None
    expense: Decimal | None
    net: Decimal | None


class CashFlowResponse(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    reporting_currency: str
    # True when at least one month could not be converted — the totals then
    # cover only the months that did.
    incomplete: bool = False
    points: list[CashFlowPoint]
    total_income: Decimal
    total_expense: Decimal
    total_net: Decimal
