"""Pure calculation boundaries for asset depreciation projections."""
from datetime import date
from decimal import Decimal, getcontext

import pytest

from app.services.asset_depreciation_service import (
    next_quarterly_revaluation_due,
    project_value,
    validate_depreciation_inputs,
)


def _project(**overrides):
    params = {
        "mode": "straight_line",
        "acquisition_date": date(2024, 2, 29),
        "acquisition_cost": Decimal("1200000.00"),
        "residual_value": Decimal("200000.00"),
        "useful_life_years": 4,
        "annual_depreciation_rate": None,
        "as_of_date": date(2026, 2, 28),
    }
    params.update(overrides)
    return project_value(**params)


def test_straight_line_uses_calendar_anniversaries_for_leap_day_acquisition():
    projection = _project()
    assert projection.value == Decimal("700000.00")
    assert projection.accumulated_depreciation == Decimal("500000.00")


@pytest.mark.parametrize("as_of", [date(2024, 2, 28), date(2024, 2, 29)])
def test_projection_before_or_on_acquisition_date_keeps_full_cost(as_of):
    projection = _project(as_of_date=as_of)
    assert projection.value == Decimal("1200000.00")
    assert projection.accumulated_depreciation == Decimal("0.00")


def test_straight_line_uses_actual_leap_year_length_for_partial_year():
    projection = _project(
        acquisition_date=date(2024, 1, 1),
        acquisition_cost=Decimal("1000"),
        residual_value=Decimal("0"),
        useful_life_years=1,
        as_of_date=date(2024, 7, 1),
    )
    assert projection.value == Decimal("502.73")
    assert projection.accumulated_depreciation == Decimal("497.27")


@pytest.mark.parametrize("residual, expected", [(Decimal("200000"), Decimal("200000.00")), (None, Decimal("0.00"))])
def test_straight_line_stops_at_residual_value(residual, expected):
    projection = _project(residual_value=residual, as_of_date=date(2035, 1, 1))
    assert projection.value == expected


def test_missing_residual_is_equivalent_to_zero():
    implicit = _project(residual_value=None)
    explicit = _project(residual_value=Decimal("0"))
    assert implicit == explicit


def test_zero_acquisition_cost_stays_zero():
    projection = _project(acquisition_cost=Decimal("0"), residual_value=Decimal("0"))
    assert projection.value == Decimal("0.00")
    assert projection.accumulated_depreciation == Decimal("0.00")


@pytest.mark.parametrize("life", [None, 0, 101])
def test_straight_line_rejects_invalid_useful_life(life):
    with pytest.raises(ValueError):
        _project(useful_life_years=life)


@pytest.mark.parametrize("rate", [None, Decimal("0"), Decimal("100"), Decimal("-5")])
def test_annual_percentage_rejects_invalid_rate(rate):
    with pytest.raises(ValueError):
        _project(mode="annual_percentage", useful_life_years=None, annual_depreciation_rate=rate)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        _project(mode="market_feed")


def test_annual_percentage_applies_discrete_completed_years():
    projection = _project(
        mode="annual_percentage",
        acquisition_date=date(2024, 1, 1),
        acquisition_cost=Decimal("1000000"),
        residual_value=None,
        useful_life_years=None,
        annual_depreciation_rate=Decimal("20"),
        as_of_date=date(2026, 1, 1),
    )
    assert projection.value == Decimal("640000.00")
    assert projection.accumulated_depreciation == Decimal("360000.00")


def test_annual_percentage_interpolates_linearly_within_year():
    projection = _project(
        mode="annual_percentage",
        acquisition_date=date(2024, 1, 1),
        acquisition_cost=Decimal("1000000"),
        residual_value=None,
        useful_life_years=None,
        annual_depreciation_rate=Decimal("20"),
        as_of_date=date(2024, 7, 1),
    )
    assert projection.value == Decimal("900546.45")


def test_projection_is_independent_of_global_decimal_precision():
    original = getcontext().prec
    try:
        getcontext().prec = 6
        low_precision = _project(as_of_date=date(2025, 7, 1))
        getcontext().prec = 28
        normal_precision = _project(as_of_date=date(2025, 7, 1))
    finally:
        getcontext().prec = original
    assert low_precision == normal_precision


@pytest.mark.parametrize("mode", ["straight_line", "annual_percentage"])
@pytest.mark.parametrize("as_of", [date(2024, 2, 29), date(2024, 8, 15), date(2028, 2, 29)])
def test_cost_always_equals_projection_plus_accumulated(mode, as_of):
    overrides = {"mode": mode, "as_of_date": as_of}
    if mode == "annual_percentage":
        overrides.update(useful_life_years=None, annual_depreciation_rate=Decimal("20"))
    projection = _project(**overrides)
    assert Decimal("1200000.00") == projection.value + projection.accumulated_depreciation


@pytest.mark.parametrize("mode", ["straight_line", "annual_percentage"])
def test_projection_is_monotonically_non_increasing(mode):
    overrides = {"mode": mode}
    if mode == "annual_percentage":
        overrides.update(useful_life_years=None, annual_depreciation_rate=Decimal("20"))
    values = [
        _project(as_of_date=date(year, month, 28), **overrides).value
        for year in range(2024, 2029)
        for month in range(1, 13)
    ]
    assert values == sorted(values, reverse=True)


@pytest.mark.parametrize(
    ("last_date", "expected"),
    [
        (date(2024, 11, 30), date(2025, 2, 28)),
        (date(2027, 11, 30), date(2028, 2, 29)),
        (date(2024, 10, 15), date(2025, 1, 15)),
        (date(2024, 12, 31), date(2025, 3, 31)),
        (date(2024, 1, 31), date(2024, 4, 30)),
    ],
)
def test_quarterly_due_date_uses_calendar_months(last_date, expected):
    assert next_quarterly_revaluation_due(last_date) == expected


def test_validation_ignores_inert_fields_for_manual_only():
    validate_depreciation_inputs(
        mode="manual_only",
        acquisition_date=None,
        acquisition_cost=Decimal("-1"),
        residual_value=Decimal("99"),
        useful_life_years=0,
        annual_depreciation_rate=Decimal("100"),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"acquisition_date": None},
        {"acquisition_cost": None},
        {"acquisition_cost": Decimal("-1")},
        {"residual_value": Decimal("-1")},
        {"residual_value": Decimal("1200000.01")},
    ],
)
def test_validation_rejects_inconsistent_shared_inputs(overrides):
    params = {
        "mode": "straight_line",
        "acquisition_date": date(2024, 1, 1),
        "acquisition_cost": Decimal("1200000"),
        "residual_value": Decimal("0"),
        "useful_life_years": 4,
        "annual_depreciation_rate": None,
    }
    params.update(overrides)
    with pytest.raises(ValueError):
        validate_depreciation_inputs(**params)
