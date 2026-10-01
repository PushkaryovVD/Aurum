from decimal import Decimal

import pytest

from app.core.financial import (
    FinancialValueError,
    allocate_largest_remainder,
    canonical_decimal,
    parse_decimal_string,
    quantize_kzt,
    quantize_posting,
    quantize_rate,
    require_scale,
)


def test_decimal_transport_accepts_only_plain_json_strings():
    assert parse_decimal_string("001.2300") == Decimal("1.2300")
    assert canonical_decimal(Decimal("001.2300")) == "1.23"

    for invalid in (1, 0.1, "1e-6", "NaN", "Infinity", "1,25", "", " 1.2"):
        with pytest.raises(FinancialValueError):
            parse_decimal_string(invalid)  # type: ignore[arg-type]


def test_precision_policy_rejects_fractional_and_integer_overflow():
    assert require_scale(Decimal("999999999999999999.123456"), precision=24, scale=6) == Decimal(
        "999999999999999999.123456"
    )

    for invalid in (Decimal("0.0000001"), Decimal("1000000000000000000")):
        with pytest.raises(FinancialValueError):
            require_scale(invalid, precision=24, scale=6)


def test_rounding_happens_only_at_explicit_boundaries_with_half_even():
    assert quantize_posting(Decimal("1.0000005")) == Decimal("1.000000")
    assert quantize_posting(Decimal("1.0000015")) == Decimal("1.000002")
    assert quantize_kzt(Decimal("2.345")) == Decimal("2.34")
    assert quantize_kzt(Decimal("2.355")) == Decimal("2.36")


@pytest.mark.parametrize("quantizer", [quantize_posting, quantize_kzt, quantize_rate])
@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_rounding_boundaries_reject_non_finite_values(quantizer, value):
    with pytest.raises(FinancialValueError):
        quantizer(value)


def test_largest_remainder_preserves_signed_parent_total():
    assert allocate_largest_remainder(Decimal("0.01"), [Decimal("1"), Decimal("1"), Decimal("1")]) == [
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    assert allocate_largest_remainder(Decimal("-0.02"), [Decimal("1"), Decimal("1"), Decimal("1")]) == [
        Decimal("-0.01"),
        Decimal("-0.01"),
        Decimal("0.00"),
    ]


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_largest_remainder_rejects_non_finite_totals_and_weights(value):
    with pytest.raises(FinancialValueError):
        allocate_largest_remainder(value, [Decimal("1")])
    with pytest.raises(FinancialValueError):
        allocate_largest_remainder(Decimal("1"), [value])