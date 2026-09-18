from decimal import Decimal

from app.services.exchange_rate_service import _parse_rate


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
