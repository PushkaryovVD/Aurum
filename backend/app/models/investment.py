"""Manual securities portfolios, trades, dividends and dated prices."""
from datetime import date as date_

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SecurityTradeType
from app.models.mixins import TimestampMixin


class InvestmentPortfolio(Base, TimestampMixin):
    __tablename__ = "investment_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship()
    securities: Mapped[list["Security"]] = relationship(back_populates="portfolio")


class Security(Base, TimestampMixin):
    __tablename__ = "securities"

    # The underlying Asset carries net-worth class/risk/valuations.
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("investment_portfolios.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    asset: Mapped["Asset"] = relationship()
    portfolio: Mapped[InvestmentPortfolio] = relationship(back_populates="securities")
    trades: Mapped[list["SecurityTrade"]] = relationship(back_populates="security", cascade="all, delete-orphan")
    dividends: Mapped[list["SecurityDividend"]] = relationship(back_populates="security", cascade="all, delete-orphan")
    prices: Mapped[list["SecurityPrice"]] = relationship(back_populates="security", cascade="all, delete-orphan")


class SecurityTrade(Base, TimestampMixin):
    __tablename__ = "security_trades"
    __table_args__ = (UniqueConstraint("asset_id", "external_id", name="uq_security_trade_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False)
    type: Mapped[SecurityTradeType] = mapped_column(
        Enum(SecurityTradeType, name="security_trade_type", native_enum=False, length=10), nullable=False
    )
    quantity: Mapped[Numeric] = mapped_column(Numeric(38, 12), nullable=False)
    price_per_unit: Mapped[Numeric] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    exchange_rate_to_kzt: Mapped[Numeric] = mapped_column(Numeric(20, 10), nullable=False)
    cash_transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False)
    fee_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(150), nullable=True)

    security: Mapped[Security] = relationship(back_populates="trades")


class SecurityDividend(Base, TimestampMixin):
    __tablename__ = "security_dividends"
    __table_args__ = (UniqueConstraint("asset_id", "external_id", name="uq_security_dividend_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False)
    gross_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    exchange_rate_to_kzt: Mapped[Numeric] = mapped_column(Numeric(20, 10), nullable=False)
    income_transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False)
    tax_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(150), nullable=True)

    security: Mapped[Security] = relationship(back_populates="dividends")

    @property
    def net_amount(self):
        return self.gross_amount - self.tax_amount


class SecurityPrice(Base):
    __tablename__ = "security_prices"
    __table_args__ = (UniqueConstraint("asset_id", "as_of_date", name="uq_security_price_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False)
    price_per_unit: Mapped[Numeric] = mapped_column(Numeric(20, 8), nullable=False)
    as_of_date: Mapped[date_] = mapped_column(Date, nullable=False)
    exchange_rate_to_kzt: Mapped[Numeric] = mapped_column(Numeric(20, 10), nullable=False)

    security: Mapped[Security] = relationship(back_populates="prices")
