"""KZT → reporting-currency conversion rules (no database needed)."""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from app.services import reporting_currency
from app.services.reporting_currency import CachedRate, ReportingConverter, kzt_to_reporting, month_end, pick_cached_rate


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the converter's one rate query with fixed rows."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def execute(self, _statement):
        self.queries += 1
        return _Rows(self.rows)


RATES = [
    CachedRate(date(2026, 8, 1), Decimal("450")),
    CachedRate(date(2026, 8, 31), Decimal("500")),
]


def test_month_end_handles_leap_february():
    assert month_end(2028, 2) == date(2028, 2, 29)
    assert month_end(2026, 12) == date(2026, 12, 31)


def test_pick_cached_rate_prefers_the_latest_on_or_before_the_date():
    assert pick_cached_rate(RATES, date(2026, 8, 31)).rate_to_kzt == Decimal("500")
    assert pick_cached_rate(RATES, date(2026, 8, 30)).rate_to_kzt == Decimal("450")
    assert pick_cached_rate(RATES, date(2027, 1, 1)).rate_to_kzt == Decimal("500")


def test_pick_cached_rate_falls_back_to_the_nearest_later_rate():
    assert pick_cached_rate(RATES, date(2026, 1, 1)).rate_to_kzt == Decimal("450")
    assert pick_cached_rate([], date(2026, 1, 1)) is None


def test_kzt_to_reporting_rounds_half_up_to_cents():
    assert kzt_to_reporting(Decimal("2751025"), Decimal("458.5")) == Decimal("6000.05")
    assert kzt_to_reporting(Decimal("0.025"), Decimal("1")) == Decimal("0.03")
    assert kzt_to_reporting(Decimal("-0.025"), Decimal("1")) == Decimal("-0.03")


async def test_kzt_reporting_is_the_identity_and_never_queries():
    session = _FakeSession(rows=[])
    converter = ReportingConverter(session, "kzt")
    assert await converter.convert(Decimal("1234.567"), date(2026, 8, 31)) == Decimal("1234.567")
    assert session.queries == 0
    assert converter.incomplete is False


async def test_convert_uses_the_period_end_rate_and_caches_the_lookup():
    session = _FakeSession(rows=[(row.requested_date, row.rate_to_kzt) for row in RATES])
    converter = ReportingConverter(session, "USD", today=date(2026, 10, 27))
    assert await converter.convert_month(Decimal("500000"), 2026, 8) == Decimal("1000.00")
    assert await converter.convert(Decimal("450"), date(2026, 8, 15)) == Decimal("1.00")
    assert session.queries == 1


async def test_a_future_period_end_uses_todays_rate():
    session = _FakeSession(rows=[(row.requested_date, row.rate_to_kzt) for row in RATES])
    converter = ReportingConverter(session, "USD", today=date(2026, 8, 15))
    # 2026-08-31 is still ahead: today's (Aug 15) rate is the Aug 1 one.
    assert await converter.convert_month(Decimal("450"), 2026, 8) == Decimal("1.00")


async def test_missing_rate_returns_none_and_marks_incomplete(monkeypatch):
    calls = []

    async def _unavailable(*args, **kwargs):
        calls.append(args)
        raise HTTPException(status_code=503, detail="NBK unavailable")

    monkeypatch.setattr(reporting_currency, "get_exchange_rate", _unavailable)
    converter = ReportingConverter(_FakeSession(rows=[]), "EUR", today=date(2026, 10, 27))

    assert await converter.convert(Decimal("0"), date(2026, 8, 31)) == Decimal("0.00")
    assert converter.incomplete is False
    assert await converter.convert(None, date(2026, 8, 31)) is None
    assert converter.incomplete is False

    assert await converter.convert(Decimal("100"), date(2026, 8, 31)) is None
    assert await converter.convert(Decimal("100"), date(2026, 9, 30)) is None
    assert converter.incomplete is True
    # One bounded cold attempt per request, not one per period.
    assert len(calls) == 1
