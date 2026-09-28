from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Money = Decimal


class MonthRef(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class EnvelopeAllocationInput(BaseModel):
    assigned_amount: Money = Field(ge=0, max_digits=14, decimal_places=2)
    planned_amount: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    rollover_positive: bool | None = None
    rollover_negative: bool | None = None


class EnvelopeMoveInput(BaseModel):
    from_category_id: int
    to_category_id: int
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)


class EnvelopeWarning(BaseModel):
    code: str
    category_id: int | None = None
    amount: Money | None = None
    closed_activity_total: Money | None = None
    current_activity_total: Money | None = None
    earliest_date: str | None = None


class EnvelopeItem(BaseModel):
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    is_unbudgeted: bool
    planned_amount: Money
    assigned_amount: Money
    activity: Money
    carried_in: Money
    available: Money
    is_overspent: bool
    rollover_positive: bool
    rollover_negative: bool
    has_row: bool


class EnvelopeStatus(BaseModel):
    year: int
    month: int
    tracking_start: MonthRef | None
    is_closed: bool
    has_ledger_drift: bool
    fx_incomplete: bool
    income: Money
    assigned: Money
    available_to_assign: Money
    items: list[EnvelopeItem]
    warnings: list[EnvelopeWarning]


class EnvelopeMonthSummary(BaseModel):
    year: int
    month: int
    is_closed: bool
    has_ledger_drift: bool


class EnvelopeAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    category_id: int | None
    from_category_id: int | None
    to_category_id: int | None
    amount: Money
    note: str | None
    created_at: datetime


class EnvelopeTemplateItemInput(BaseModel):
    category_id: int
    planned_amount: Money = Field(ge=0, max_digits=14, decimal_places=2)
    rollover_positive: bool = True
    rollover_negative: bool = True


class EnvelopeTemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    items: list[EnvelopeTemplateItemInput] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_categories(self):
        ids = [item.category_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Template categories must be unique")
        return self


class EnvelopeTemplateItemRead(EnvelopeTemplateItemInput):
    id: int


class EnvelopeTemplateRead(BaseModel):
    id: int
    name: str
    items: list[EnvelopeTemplateItemRead]


class EnvelopeFundInput(BaseModel):
    template_id: int | None = None
    copy_plan_from: MonthRef | None = None


class EnvelopeShortfall(BaseModel):
    category_id: int
    shortfall: Money


class EnvelopeFundResult(BaseModel):
    status: EnvelopeStatus
    unfunded: list[EnvelopeShortfall]
