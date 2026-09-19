from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.exchange_rate import ExchangeRate
from app.services.exchange_rate_service import _parse_rate, cross_ratio


def test_parse_rate_normalizes_nbk_quoted_quantity():
    xml = b"""<?xml version='1.0' encoding='utf-8'?>
    <rates><item><title>KRW</title><description>32.55</description><quant>100</quant></item></rates>
    """
    assert _parse_rate(xml, "KRW") == Decimal("0.3255")


def test_parse_rate_accepts_decimal_comma():
    xml = b"""<rates><item><title>USD</title><description>444,88</description><quant>1</quant></item></rates>"""
    assert _parse_rate(xml, "USD") == Decimal("444.88")


def test_parse_rate_returns_none_for_unknown_currency():
    xml = b"""<rates><item><title>USD</title><description>444.88</description><quant>1</quant></item></rates>"""
    assert _parse_rate(xml, "EUR") is None


def test_cross_ratio_divides_the_two_legs():
    source = ExchangeRate(currency="USD", rate_to_kzt=Decimal("500"))
    target = ExchangeRate(currency="EUR", rate_to_kzt=Decimal("550"))

    assert cross_ratio(source, target) == Decimal("0.909091")


def test_cross_ratio_rejects_a_zero_leg():
    """A zero would divide by zero; the guard turns it into a clear 422 instead
    of a 500 from somewhere deeper."""
    source = ExchangeRate(currency="USD", rate_to_kzt=Decimal("500"))
    target = ExchangeRate(currency="EUR", rate_to_kzt=Decimal("0"))

    with pytest.raises(HTTPException):
        cross_ratio(source, target)
