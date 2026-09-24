from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AssetClass, AssetValuationMode, CapitalRole, RiskLevel


class AssetValuationCreate(BaseModel):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)
    exchange_rate_to_kzt: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)


class AssetValuationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    value: Decimal
    exchange_rate_to_kzt: Decimal | None
    base_value_kzt: Decimal | None
    as_of_date: date_


class AssetRevaluationReminderRead(BaseModel):
    asset_id: int
    asset_name: str
    due_date: date_
    projected_value: Decimal
    latest_market_value: Decimal
    latest_market_value_date: date_


class AssetRevaluationAccept(BaseModel):
    as_of_date: date_ = Field(default_factory=date_.today)


class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    asset_class: AssetClass
    currency: str = Field(default="KZT", min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=2000)
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    # Rough self-reported monthly net cash flow — informational, not tracked
    # transactions (see Asset.monthly_cash_flow).
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    acquisition_date: date_ | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    residual_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    valuation_mode: AssetValuationMode = AssetValuationMode.MANUAL_ONLY
    useful_life_years: int | None = Field(default=None, ge=1, le=100)
    annual_depreciation_rate: Decimal | None = Field(default=None, gt=0, lt=100, max_digits=7, decimal_places=4)

    @model_validator(mode="after")
    def validate_depreciation_inputs(self) -> "AssetBase":
        if self.residual_value is not None and self.acquisition_cost is not None and self.residual_value > self.acquisition_cost:
            raise ValueError("residual_value cannot exceed acquisition_cost")
        if self.valuation_mode == AssetValuationMode.MANUAL_ONLY:
            return self
        if self.acquisition_date is None or self.acquisition_cost is None:
            raise ValueError("depreciation requires acquisition_date and acquisition_cost")
        if self.valuation_mode == AssetValuationMode.STRAIGHT_LINE and self.useful_life_years is None:
            raise ValueError("straight_line requires useful_life_years")
        if self.valuation_mode == AssetValuationMode.ANNUAL_PERCENTAGE and self.annual_depreciation_rate is None:
            raise ValueError("annual_percentage requires annual_depreciation_rate")
        return self


class AssetCreate(AssetBase):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)
    exchange_rate_to_kzt: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    asset_class: AssetClass | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=2000)
    capital_role: CapitalRole | None = None
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel | None = None
    acquisition_date: date_ | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    residual_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    valuation_mode: AssetValuationMode | None = None
    useful_life_years: int | None = Field(default=None, ge=1, le=100)
    annual_depreciation_rate: Decimal | None = Field(default=None, gt=0, lt=100, max_digits=7, decimal_places=4)


class AssetRead(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_value: Decimal
    current_base_value_kzt: Decimal | None
    as_of_date: date_
    projected_value: Decimal | None
    accumulated_depreciation: Decimal | None
    latest_market_value: Decimal | None
    latest_market_value_date: date_ | None
    unrealized_change: Decimal | None
