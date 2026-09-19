"""A single money movement: income, expense, or a transfer between accounts."""
from datetime import date as date_

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ExchangeRateSource, TransactionPurpose, TransactionType
from app.models.mixins import TimestampMixin
from app.models.tag import transaction_tags


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "external_id", name="uq_transaction_account_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Destination account for TRANSFER-type rows only.
    transfer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=False, length=10), nullable=False
    )
    # Always stored positive; `type` carries the sign/direction.
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    # Immutable conversion snapshot used by cross-account reports. `amount`
    # remains the real account-currency movement and therefore still drives
    # the account balance.
    exchange_rate_to_kzt: Mapped[Numeric | None] = mapped_column(Numeric(20, 10), nullable=True)
    base_amount_kzt: Mapped[Numeric | None] = mapped_column(Numeric(18, 2), nullable=True)
    exchange_rate_source: Mapped[ExchangeRateSource | None] = mapped_column(
        Enum(ExchangeRateSource, name="exchange_rate_source", native_enum=False, length=10), nullable=True
    )
    # Ledger currency of this transaction — the currency the user actually
    # paid in, which is not necessarily the account's. A card purchase abroad
    # is denominated here in the foreign currency while `amount` still holds
    # what the account was really debited; defaults to the account currency.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KZT")
    # Amount in `currency`. Equals `amount` for a same-currency operation and
    # differs from it only when the transaction and account currencies don't
    # match (then the effective rate is amount / transaction_amount).
    transaction_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    # Destination-side movement for a transfer. It equals amount for same-
    # currency accounts and may differ for FX transfers.
    transfer_amount: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(150), nullable=True)
    purpose: Mapped[TransactionPurpose] = mapped_column(
        Enum(TransactionPurpose, name="transaction_purpose", native_enum=False, length=20),
        nullable=False,
        default=TransactionPurpose.ORDINARY,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[date_] = mapped_column(Date, nullable=False)

    account: Mapped["Account"] = relationship(back_populates="transactions", foreign_keys=[account_id])
    transfer_account: Mapped["Account | None"] = relationship(foreign_keys=[transfer_account_id])
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    tags: Mapped[list["Tag"]] = relationship(secondary=transaction_tags, back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionSplit.id"
    )


class TransactionSplit(Base):
    """One category's slice of a transaction whose amount is divided across
    several categories (one receipt, several kinds of goods) — an
    alternative to Transaction.category_id, not an addition to it: a split
    transaction has category_id=NULL and two or more of these instead, and
    their amounts must add up to the parent's amount exactly (see
    schemas/transaction.py's split_rule_violation).

    category_id is nullable + SET NULL, same as Transaction.category_id
    itself — deleting a category must not break *reading* a split that used
    to point at it, only creating/editing one requires a live category (see
    routes/transactions.py, and the same lesson already applied to
    transfer_account_id)."""

    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="splits")
    category: Mapped["Category | None"] = relationship()
