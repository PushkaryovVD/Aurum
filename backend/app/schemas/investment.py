from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SecurityTradeType


class InvestmentPortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_id: int


class InvestmentPortfolioRead(InvestmentPortfolioCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_archived: bool


class SecurityCreate(BaseModel):
    portfolio_id: int
    name: str = Field(min_length=1, max_length=150)
    ticker: str = Field(min_length=1, max_length=30)
    isin: str | None = Field(default=None, min_length=12, max_length=12)
    exchange: str | None = Field(default=None, max_length=50)
    currency: str = Field(min_length=3, max_length=3)


class SecurityTradeCreate(BaseModel):
    type: SecurityTradeType
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=12)
    price_per_unit: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    fee: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    date: date_
    exchange_rate_to_kzt: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)
    external_id: str | None = Field(default=None, max_length=150)


class SecurityDividendCreate(BaseModel):
    gross_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    date: date_
    exchange_rate_to_kzt: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)
    external_id: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def _tax_not_above_gross(self):
        if self.tax_amount > self.gross_amount:
            raise ValueError("tax_amount cannot exceed gross_amount")
        return self


class SecurityPriceCreate(BaseModel):
    price_per_unit: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    as_of_date: date_
    exchange_rate_to_kzt: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)


class SecurityTradeRead(SecurityTradeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SecurityDividendRead(SecurityDividendCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    net_amount: Decimal


class SecurityPositionRead(BaseModel):
    asset_id: int
    portfolio_id: int
    name: str
    ticker: str
    isin: str | None
    exchange: str | None
    currency: str
    quantity: Decimal
    average_cost: Decimal | None
    cost_basis: Decimal
    current_price: Decimal | None
    current_value: Decimal | None
    realized_profit: Decimal
    unrealized_profit: Decimal | None
    net_dividends: Decimal
    total_return: Decimal
    trades: list[SecurityTradeRead]
    dividends: list[SecurityDividendRead]
