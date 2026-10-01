"""Central decimal policy for authoritative financial calculations.

Values stay exact through intermediate arithmetic.  The helpers below are the
only supported posting/report rounding boundaries and deliberately use a local
context so unrelated code cannot change financial results globally.
"""
from decimal import Context, Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
import re
from collections.abc import Sequence

MONEY_PRECISION = 24
MONEY_SCALE = 6
QUANTITY_PRECISION = 38
QUANTITY_SCALE = 18
RATE_PRECISION = 38
RATE_SCALE = 18
PERCENT_PRECISION = 18
PERCENT_SCALE = 8
KZT_PRECISION = 24
KZT_SCALE = 2

FINANCIAL_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
PLAIN_DECIMAL_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


class FinancialValueError(ValueError):
    """A value cannot be represented under Aurum's financial contract."""


def parse_decimal_string(value: str) -> Decimal:
    """Parse the API wire format without accepting JSON numbers or exponents."""
    if not isinstance(value, str) or not PLAIN_DECIMAL_RE.fullmatch(value):
        raise FinancialValueError("financial values must be plain decimal JSON strings")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FinancialValueError("invalid decimal value") from exc
    if not parsed.is_finite():
        raise FinancialValueError("financial values must be finite")
    return parsed


def canonical_decimal(value: Decimal) -> str:
    """Serialize a finite Decimal without exponent or insignificant zeroes."""
    if not value.is_finite():
        raise FinancialValueError("financial values must be finite")
    if value.is_zero():
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def require_scale(value: Decimal, *, precision: int, scale: int) -> Decimal:
    """Reject, rather than round, values outside an explicit NUMERIC policy."""
    if not value.is_finite():
        raise FinancialValueError("financial values must be finite")
    normalized = value.copy_abs()
    exponent = normalized.as_tuple().exponent
    fractional_digits = max(-exponent, 0)
    if fractional_digits > scale:
        raise FinancialValueError(f"value has more than {scale} fractional digits")
    integer_digits = max(normalized.adjusted() + 1, 0) if normalized else 0
    if integer_digits > precision - scale:
        raise FinancialValueError(f"value exceeds NUMERIC({precision}, {scale})")
    return value


def _quantize(value: Decimal, scale: int) -> Decimal:
    if not value.is_finite():
        raise FinancialValueError("financial values must be finite")
    with localcontext(FINANCIAL_CONTEXT):
        return value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN)


def quantize_posting(value: Decimal) -> Decimal:
    return _quantize(value, MONEY_SCALE)


def quantize_kzt(value: Decimal) -> Decimal:
    return _quantize(value, KZT_SCALE)


def quantize_rate(value: Decimal) -> Decimal:
    return _quantize(value, RATE_SCALE)


def allocate_largest_remainder(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Allocate a rounded KZT total deterministically while preserving its sum."""
    if not total.is_finite() or any(not weight.is_finite() for weight in weights):
        raise FinancialValueError("financial values must be finite")
    if not weights or any(weight < 0 for weight in weights) or sum(weights, Decimal(0)) <= 0:
        raise FinancialValueError("allocation weights must contain a positive total")
    total = quantize_kzt(total)
    sign = Decimal(-1) if total < 0 else Decimal(1)
    unit = Decimal("0.01")
    absolute_total = abs(total)
    weight_total = sum(weights, Decimal(0))
    with localcontext(FINANCIAL_CONTEXT):
        exact = [absolute_total * weight / weight_total for weight in weights]
        floors = [value.quantize(unit, rounding=ROUND_FLOOR) for value in exact]
    remaining_units = int((absolute_total - sum(floors, Decimal(0))) / unit)
    order = sorted(range(len(weights)), key=lambda index: (-(exact[index] - floors[index]), index))
    for index in order[:remaining_units]:
        floors[index] += unit
    return [amount * sign for amount in floors]
