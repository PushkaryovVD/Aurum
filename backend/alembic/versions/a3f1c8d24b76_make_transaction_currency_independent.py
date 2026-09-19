"""make transaction currency independent of the account currency

Replaces the original_* triple — merchant-currency detail bolted onto an
account-currency row — with a first-class transaction currency: `currency`
plus `transaction_amount`. `amount` keeps meaning "what the account was
actually debited", so every balance, report and net-worth calculation stays
exactly as it was.

Revision ID: a3f1c8d24b76
Revises: f5d8b2c7a410
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a3f1c8d24b76"
down_revision: str | None = "f5d8b2c7a410"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("transaction_amount", sa.Numeric(14, 2), nullable=True))
    # A row that carried merchant-currency detail becomes a row denominated in
    # that currency; every other row keeps the account's. Either way
    # transaction_amount holds what the user originally typed, and `amount` is
    # left untouched so no balance moves.
    op.execute(
        """
        UPDATE transactions AS t
        SET currency = upper(coalesce(t.original_currency, a.currency)),
            transaction_amount = coalesce(t.original_amount, t.amount)
        FROM accounts AS a
        WHERE a.id = t.account_id
        """
    )
    op.alter_column("transactions", "currency", nullable=False)
    op.alter_column("transactions", "transaction_amount", nullable=False)
    op.drop_column("transactions", "original_amount")
    op.drop_column("transactions", "original_currency")
    op.drop_column("transactions", "original_to_account_rate")


def downgrade() -> None:
    op.add_column("transactions", sa.Column("original_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("transactions", sa.Column("original_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("original_to_account_rate", sa.Numeric(20, 10), nullable=True))
    # Only a genuinely foreign-currency row can be restored as merchant detail;
    # a same-currency row never carried any, so it stays NULL as before.
    op.execute(
        """
        UPDATE transactions AS t
        SET original_currency = t.currency,
            original_amount = t.transaction_amount,
            original_to_account_rate = CASE
                WHEN t.transaction_amount <> 0 THEN t.amount / t.transaction_amount
                ELSE NULL
            END
        FROM accounts AS a
        WHERE a.id = t.account_id
          AND upper(t.currency) <> upper(a.currency)
        """
    )
    op.drop_column("transactions", "transaction_amount")
    op.drop_column("transactions", "currency")
