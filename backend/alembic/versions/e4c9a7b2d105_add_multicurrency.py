"""add multicurrency transaction snapshots and NBK rate cache

Revision ID: e4c9a7b2d105
Revises: d1a6f4c8b729
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e4c9a7b2d105"
down_revision: str | None = "d1a6f4c8b729"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requested_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_to_kzt", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("requested_date", "currency", name="uq_exchange_rate_date_currency"),
    )
    op.add_column("asset_valuations", sa.Column("exchange_rate_to_kzt", sa.Numeric(20, 10), nullable=True))
    op.add_column("asset_valuations", sa.Column("base_value_kzt", sa.Numeric(18, 2), nullable=True))
    op.add_column("transactions", sa.Column("exchange_rate_to_kzt", sa.Numeric(20, 10), nullable=True))
    op.add_column("transactions", sa.Column("base_amount_kzt", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "transactions",
        sa.Column(
            "exchange_rate_source",
            sa.Enum("NBK", "MANUAL", "CSV", name="exchange_rate_source", native_enum=False, length=10),
            nullable=True,
        ),
    )
    op.add_column("transactions", sa.Column("original_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("transactions", sa.Column("original_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("original_to_account_rate", sa.Numeric(20, 10), nullable=True))
    op.add_column("transactions", sa.Column("transfer_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("transactions", sa.Column("external_id", sa.String(length=150), nullable=True))
    op.add_column(
        "transactions",
        sa.Column(
            "purpose",
            sa.Enum(
                "ORDINARY", "INVESTMENT_TRADE", "DIVIDEND", "FEE", "TAX",
                name="transaction_purpose", native_enum=False, length=20,
            ),
            nullable=False,
            server_default="ORDINARY",
        ),
    )
    op.create_unique_constraint("uq_transaction_account_external_id", "transactions", ["account_id", "external_id"])
    # Existing KZT rows are fully known. Other currencies intentionally stay
    # nullable until the explicit historical sync can obtain an official rate.
    op.execute(
        """
        UPDATE transactions AS t
        SET exchange_rate_to_kzt = 1,
            base_amount_kzt = t.amount,
            exchange_rate_source = 'NBK',
            transfer_amount = CASE WHEN t.type = 'TRANSFER' THEN t.amount ELSE NULL END
        FROM accounts AS a
        WHERE a.id = t.account_id AND upper(a.currency) = 'KZT'
        """
    )
    op.execute(
        """
        UPDATE asset_valuations AS v
        SET exchange_rate_to_kzt = 1, base_value_kzt = v.value
        FROM assets AS a
        WHERE a.id = v.asset_id AND upper(a.currency) = 'KZT'
        """
    )


def downgrade() -> None:
    op.drop_column("asset_valuations", "base_value_kzt")
    op.drop_column("asset_valuations", "exchange_rate_to_kzt")
    op.drop_constraint("uq_transaction_account_external_id", "transactions", type_="unique")
    for column in (
        "purpose", "external_id", "transfer_amount", "original_to_account_rate",
        "original_currency", "original_amount", "exchange_rate_source",
        "base_amount_kzt", "exchange_rate_to_kzt",
    ):
        op.drop_column("transactions", column)
    op.drop_table("exchange_rates")
