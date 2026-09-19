"""User-defined rules that assign a category from what a transaction looks like.

Rules are ordered and the **first enabled match wins** — the order is the whole
point, because a specific rule ("Yandex Go" → Transport / Taxi) has to be able
to outrank a broad one ("Яндекс" → Transport) without the user deleting either.

Nothing here ever rewrites history on its own: rules are applied while a
transaction is being entered or previewed, and to existing rows only through a
separate, explicitly previewed bulk action.
"""
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MatchType, TransactionType
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category


class CategorizationRule(Base, TimestampMixin):
    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Lower runs first. Kept dense (0, 1, 2 …) by the service, so reordering is
    # a plain swap rather than a fractional-index scheme.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Shown in the rules list, and in the "matched by …" hint next to a
    # transaction, so a rule is recognisable without reading its pattern.
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    match_type: Mapped[MatchType] = mapped_column(
        Enum(MatchType, name="categorization_match_type", native_enum=False, length=10),
        nullable=False,
        default=MatchType.CONTAINS,
    )
    # Tested case-insensitively against the transaction's description *or* its
    # merchant — whichever the source happened to fill in, since a bank export
    # and a manual entry rarely agree on which of the two carries the shop name.
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)

    # Optional narrowing conditions. NULL means "don't care" and is therefore
    # the default rather than a zero: a rule with no amount bound must not
    # behave like one bounded at 0.
    amount_min: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_max: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    transaction_type: Mapped[TransactionType | None] = mapped_column(
        Enum(TransactionType, name="categorization_transaction_type", native_enum=False, length=10),
        nullable=True,
    )

    # What the rule assigns. Required — a rule that assigns nothing is a
    # no-op, and CASCADE so deleting a category takes its rules with it rather
    # than leaving them pointing at nothing.
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)

    account: Mapped["Account | None"] = relationship()
    category: Mapped["Category"] = relationship()
