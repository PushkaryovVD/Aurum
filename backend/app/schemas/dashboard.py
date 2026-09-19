from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CategoryBreakdownChildItem(BaseModel):
    """One subcategory's (or the parent's own direct, un-subcategorized)
    share of a CategoryBreakdownItem's total — see
    services/category_rollup.py's CategoryRollupChildItem."""

    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal


class CategoryBreakdownItem(BaseModel):
    category_id: int | None
    name: str
    color: str
    icon: str | None
    amount: Decimal
    percent: float
    # Populated only when this slice's spend came from more than one
    # distinct category (subcategories, or a mix of the parent itself and
    # its children) — e.g. a receipt split across "Groceries" subcategories.
    children: list[CategoryBreakdownChildItem] = Field(default_factory=list)


class CurrencyBalance(BaseModel):
    """One account currency's share of the total: the raw sum of the account
    balances held in that currency, plus its converted value in the reporting
    currency. `amount_reporting` stays None when no exchange rate was
    available — the UI has to say so rather than present a foreign balance as
    if it were already in the reporting currency."""

    currency: str
    amount: Decimal
    amount_reporting: Decimal | None = None
    # The rate actually applied and the day it is effective for — carried so a
    # stale rate is visible instead of implied.
    rate_to_kzt: Decimal | None = None
    rate_date: date | None = None


class BalanceSummary(BaseModel):
    """Total money across every account, in the app's reporting currency.

    Each account keeps its balance in its own currency; this is the one place
    those get added up, and it states plainly which currency the sum is in and
    whether any part of it could not be converted."""

    reporting_currency: str
    total: Decimal
    # True when at least one currency had no usable rate — `total` then covers
    # only the currencies that did convert.
    incomplete: bool
    items: list[CurrencyBalance]


class DashboardSummary(BaseModel):
    year: int
    month: int
    real_income: Decimal
    spent: Decimal
    net: Decimal
    transferred_out: Decimal
    spending_by_category: list[CategoryBreakdownItem]
    # All-time rather than month-scoped: the money currently in the accounts.
    balance: BalanceSummary
