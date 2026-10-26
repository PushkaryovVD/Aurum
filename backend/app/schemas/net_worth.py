from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel


class NetWorthPoint(BaseModel):
    date: date_
    # In NetWorthSummary.reporting_currency at the official rate for this
    # point's own date; None when that day had value but no rate.
    value: Decimal | None


class NetWorthBreakdownItem(BaseModel):
    key: str
    name: str
    color: str
    icon: str
    amount: Decimal | None
    percent: float


class CapitalRoleSummary(BaseModel):
    """Assets grouped by how they behave month to month (see CapitalRole) —
    a cross-cut of the asset-class breakdown, not a replacement for it."""

    role: str
    label: str
    color: str
    total_value: Decimal | None
    monthly_cash_flow: Decimal
    count: int


class RiskLevelItem(BaseModel):
    """One holding within a risk tier — Cash (key="cash") or a single asset
    (key=f"asset:{id}"). This list IS the diversification view: a tier with
    one item at 100% is concentrated, several items with even shares aren't,
    no separate score needed."""

    key: str
    name: str
    amount: Decimal | None
    percent: float  # share of this tier, not of total capital


class RiskLevelSummary(BaseModel):
    """Cash + assets grouped by user-tagged risk of loss (see RiskLevel) —
    another cross-cut, like capital_roles, but Cash participates here since
    it's the zero-risk anchor an 80/20-style allocation rule needs."""

    risk_level: str
    label: str
    color: str
    total_value: Decimal | None
    percent: float  # share of total capital (cash + assets)
    items: list[RiskLevelItem]


class NetWorthSummary(BaseModel):
    range: str
    # The currency every amount here is in: the ledger's KZT values converted
    # at the official rate for each point's date (today for the current
    # totals). Percent shares are ratios of the KZT values, so always exact.
    reporting_currency: str
    # True when some non-zero value had no rate and is therefore None.
    incomplete: bool = False
    current: Decimal | None
    change_amount: Decimal | None
    change_percent: float | None
    series: list[NetWorthPoint]
    breakdown: list[NetWorthBreakdownItem]
    capital_roles: list[CapitalRoleSummary]
    risk_levels: list[RiskLevelSummary]
