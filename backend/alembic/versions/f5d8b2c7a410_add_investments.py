"""add investment portfolios, securities and events

Revision ID: f5d8b2c7a410
Revises: e4c9a7b2d105
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f5d8b2c7a410"
down_revision: str | None = "e4c9a7b2d105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    op.create_table(
        "investment_portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_table(
        "securities",
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("investment_portfolios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("isin", sa.String(12)),
        sa.Column("exchange", sa.String(50)),
        sa.Column("currency", sa.String(3), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "security_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Enum("BUY", "SELL", name="security_trade_type", native_enum=False, length=10), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 12), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exchange_rate_to_kzt", sa.Numeric(20, 10), nullable=False),
        sa.Column("cash_transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fee_transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="SET NULL")),
        sa.Column("external_id", sa.String(150)),
        *_timestamps(),
        sa.UniqueConstraint("asset_id", "external_id", name="uq_security_trade_external_id"),
    )
    op.create_table(
        "security_dividends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exchange_rate_to_kzt", sa.Numeric(20, 10), nullable=False),
        sa.Column("income_transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tax_transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="SET NULL")),
        sa.Column("external_id", sa.String(150)),
        *_timestamps(),
        sa.UniqueConstraint("asset_id", "external_id", name="uq_security_dividend_external_id"),
    )
    op.create_table(
        "security_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("securities.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(20, 8), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("exchange_rate_to_kzt", sa.Numeric(20, 10), nullable=False),
        sa.UniqueConstraint("asset_id", "as_of_date", name="uq_security_price_date"),
    )


def downgrade() -> None:
    for table in ("security_prices", "security_dividends", "security_trades", "securities", "investment_portfolios"):
        op.drop_table(table)
