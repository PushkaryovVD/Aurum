from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class CategoryRankingChildItem(BaseModel):
    """One subcategory's (or the parent's own direct, un-subcategorized)
    share of a CategoryRankingItem's total — see
    services/category_rollup.py's CategoryRollupChildItem."""

    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal | None


class CategorySpendingPoint(BaseModel):
    year: int
    month: int
    # In the report's reporting_currency at the rate for the month's last
    # day; None when that month had spending but no rate.
    amount: Decimal | None


class CategorySpendingReport(BaseModel):
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    start_date: date_ | None
    end_date: date_ | None
    # Every amount in this report is in this currency; `incomplete` means
    # some month could not be converted and is left out of the totals.
    reporting_currency: str
    incomplete: bool = False
    total_amount: Decimal
    transaction_count: int
    average_per_month: Decimal
    series: list[CategorySpendingPoint]


class CategoryRankingItem(BaseModel):
    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal | None
    percent: float
    transaction_count: int
    # Populated only when this category's spend came from more than one
    # distinct category (subcategories, or a mix of itself and its
    # children) — e.g. a receipt split across "Groceries" subcategories.
    children: list[CategoryRankingChildItem] = Field(default_factory=list)


class CategoryRankingReport(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    # Period totals convert once, at the official rate for the period's end
    # (end_date, or today when it is open-ended or still in the future).
    reporting_currency: str
    incomplete: bool = False
    total_amount: Decimal | None
    items: list[CategoryRankingItem]
