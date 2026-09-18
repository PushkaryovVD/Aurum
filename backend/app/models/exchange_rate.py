"""Cached official KZT exchange rates from the National Bank of Kazakhstan."""
from datetime import date as date_, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("requested_date", "currency", name="uq_exchange_rate_date_currency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_date: Mapped[date_] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date_] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # KZT for one unit of `currency`; NBK's quoted quantity is normalized.
    rate_to_kzt: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="nbk")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
