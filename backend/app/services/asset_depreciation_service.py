"""Pure, deterministic calculations for asset depreciation projections."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

MONEY_QUANTUM = Decimal("0.01")
CALC_PRECISION = 28


@dataclass(frozen=True)
class AssetValueProjection:
    value: Decimal
    accumulated_depreciation: Decimal


def _mode_value(mode: object) -> str:
    value = getattr(mode, "value", mode)
    return str(value)


def validate_depreciation_inputs(
    *,
    mode: object,
    acquisition_date: date | None,
    acquisition_cost: Decimal | None,
    residual_value: Decimal | None,
    useful_life_years: int | None,
    annual_depreciation_rate: Decimal | None,
) -> None:
    """Validate the cross-field rules shared by API input and backup restore."""
    mode_value = _mode_value(mode)
    if mode_value == "manual_only":
        return
    if mode_value not in {"straight_line", "annual_percentage"}:
        raise ValueError("Unknown asset valuation mode")
    if acquisition_date is None or acquisition_cost is None:
        raise ValueError("Depreciation requires acquisition_date and acquisition_cost")
    if acquisition_cost < 0:
        raise ValueError("Acquisition cost cannot be negative")
    if residual_value is not None and (residual_value < 0 or residual_value > acquisition_cost):
        raise ValueError("Residual value must be between zero and acquisition cost")
    if mode_value == "straight_line" and (
        useful_life_years is None or not 1 <= useful_life_years <= 100
    ):
        raise ValueError("Straight-line depreciation requires useful_life_years between 1 and 100")
    if mode_value == "annual_percentage" and (
        annual_depreciation_rate is None
        or annual_depreciation_rate <= 0
        or annual_depreciation_rate >= 100
    ):
        raise ValueError("Annual depreciation rate must be greater than 0 and less than 100")


def _anniversary(acquisition_date: date, years: int) -> date:
    target_year = acquisition_date.year + years
    day = min(acquisition_date.day, calendar.monthrange(target_year, acquisition_date.month)[1])
    return acquisition_date.replace(year=target_year, day=day)


def _elapsed_parts(acquisition_date: date, as_of_date: date) -> tuple[int, Decimal]:
    if as_of_date <= acquisition_date:
        return 0, Decimal(0)
    completed = as_of_date.year - acquisition_date.year
    if _anniversary(acquisition_date, completed) > as_of_date:
        completed -= 1
    current = _anniversary(acquisition_date, completed)
    following = _anniversary(acquisition_date, completed + 1)
    with localcontext() as context:
        context.prec = CALC_PRECISION
        partial = Decimal((as_of_date - current).days) / Decimal((following - current).days)
    return completed, partial


def project_value(
    *,
    mode: object,
    acquisition_date: date | None,
    acquisition_cost: Decimal | None,
    residual_value: Decimal | None,
    useful_life_years: int | None,
    annual_depreciation_rate: Decimal | None,
    as_of_date: date,
) -> AssetValueProjection | None:
    """Return a read-only planning projection; never records a valuation."""
    validate_depreciation_inputs(
        mode=mode,
        acquisition_date=acquisition_date,
        acquisition_cost=acquisition_cost,
        residual_value=residual_value,
        useful_life_years=useful_life_years,
        annual_depreciation_rate=annual_depreciation_rate,
    )
    mode_value = _mode_value(mode)
    if mode_value == "manual_only":
        return None

    # Validation above narrows these values for both depreciation modes.
    assert acquisition_date is not None
    assert acquisition_cost is not None
    residual = residual_value if residual_value is not None else Decimal(0)
    completed, partial = _elapsed_parts(acquisition_date, as_of_date)

    with localcontext() as context:
        context.prec = CALC_PRECISION
        if mode_value == "straight_line":
            assert useful_life_years is not None
            elapsed = Decimal(completed) + partial
            fraction = min(elapsed / Decimal(useful_life_years), Decimal(1))
            raw_value = acquisition_cost - (acquisition_cost - residual) * fraction
        else:
            assert annual_depreciation_rate is not None
            rate = annual_depreciation_rate / Decimal(100)
            raw_value = residual + (acquisition_cost - residual) * (Decimal(1) - rate) ** completed * (
                Decimal(1) - rate * partial
            )
        raw_value = max(residual, min(acquisition_cost, raw_value))
        value = raw_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
        rounded_cost = acquisition_cost.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
        accumulated = rounded_cost - value
    return AssetValueProjection(value=value, accumulated_depreciation=accumulated)


def next_quarterly_revaluation_due(last_valuation_date: date) -> date:
    """Add three calendar months, clamping to the target month's last day."""
    zero_based_month = last_valuation_date.month - 1 + 3
    year = last_valuation_date.year + zero_based_month // 12
    month = zero_based_month % 12 + 1
    day = min(last_valuation_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
