"""Categorization rules: the wire shapes for managing them and for seeing what
they would do before anything is written."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import MatchType, TransactionType


class CategorizationRuleFields(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    match_type: MatchType = MatchType.CONTAINS
    pattern: str = Field(min_length=1, max_length=200)
    # Both bounds are optional and mean "don't care" when absent — a rule with no
    # upper bound must not behave like one bounded at zero.
    amount_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    amount_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    # Compared against the transaction's own currency, not the account's.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    account_id: int | None = None
    transaction_type: TransactionType | None = None
    category_id: int
    is_enabled: bool = True

    @field_validator("currency")
    @classmethod
    def _uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _validate_bounds(self) -> "CategorizationRuleFields":
        if self.amount_min is not None and self.amount_max is not None and self.amount_min > self.amount_max:
            raise ValueError("amount_min must not be greater than amount_max")
        return self


class CategorizationRuleCreate(CategorizationRuleFields):
    pass


class CategorizationRuleUpdate(BaseModel):
    """Partial update — omitted fields are left alone, same as every other
    PATCH in the API."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    match_type: MatchType | None = None
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    amount_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    amount_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    account_id: int | None = None
    transaction_type: TransactionType | None = None
    category_id: int | None = None
    is_enabled: bool | None = None

    @field_validator("currency")
    @classmethod
    def _uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class CategorizationRuleReorder(BaseModel):
    """The full rule order, top to bottom. Every id must exist and none may be
    missing — a partial order has no defined meaning."""

    ordered_ids: list[int] = Field(min_length=1)


class CategorizationRuleRead(CategorizationRuleFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    # Denormalised for the rules list, which always shows what a rule assigns.
    category_name: str | None = None
    category_color: str | None = None


class RuleEffectItem(BaseModel):
    """What one rule did (or would do) to the transactions it was run over."""

    rule_id: int
    name: str
    matched: int
    # A few example descriptions, so a surprising count can be judged at a
    # glance instead of taken on trust.
    samples: list[str] = Field(default_factory=list)


class RuleApplyResult(BaseModel):
    """The outcome of running the saved rules over existing transactions.

    `dry_run` reports the same numbers without touching a single row — that is
    the only way a rule set is ever evaluated before it is enabled or reordered.
    """

    dry_run: bool
    considered: int
    matched: int
    written: int
    items: list[RuleEffectItem]
