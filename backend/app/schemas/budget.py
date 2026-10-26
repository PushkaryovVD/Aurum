from decimal import Decimal

from pydantic import BaseModel, Field


class BudgetCreate(BaseModel):
    category_id: int
    monthly_limit: Decimal = Field(gt=0)


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal = Field(gt=0)


class BudgetRead(BaseModel):
    id: int
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    monthly_limit: Decimal


class BudgetStatus(BaseModel):
    """One budgeted category's actual spend for a given month, compared
    against its limit."""

    budget_id: int
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    # The limit is entered by the user in the workspace's reporting currency;
    # `spent` is the KZT ledger sum converted into that same currency (rate
    # for the month's last day), so the two are compared like for like.
    monthly_limit: Decimal
    # None when the month's spending could not be converted (no rate) — then
    # remaining/percent are unknown too and the budget is never called over.
    spent: Decimal | None
    remaining: Decimal | None
    # Can exceed 100 — the UI clamps the progress bar fill, not this number,
    # so "spent 150% of budget" is still visible in the raw value.
    percent: float | None
    is_over_budget: bool


class BudgetStatusResponse(BaseModel):
    year: int
    month: int
    # The currency of every limit and spent figure in `items`.
    reporting_currency: str
    # True when some category's spending had no rate (its `spent` is None).
    incomplete: bool = False
    items: list[BudgetStatus]
