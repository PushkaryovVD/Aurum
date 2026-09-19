"""categorization rules

Adds the ordered user rules that assign a category from a transaction's
description/merchant plus optional amount, currency, account and type bounds.
First enabled match wins, so `priority` is the column that matters.

Revision ID: b7e2c4f19a35
Revises: a3f1c8d24b76
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b7e2c4f19a35"
down_revision: str | None = "a3f1c8d24b76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categorization_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "match_type",
            sa.Enum("CONTAINS", "REGEX", name="categorization_match_type", native_enum=False, length=10),
            nullable=False,
            server_default="CONTAINS",
        ),
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column("amount_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "transaction_type",
            sa.Enum(
                "INCOME",
                "EXPENSE",
                "TRANSFER",
                name="categorization_transaction_type",
                native_enum=False,
                length=10,
            ),
            nullable=True,
        ),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Every read is "the enabled rules, in order" — the index is the order.
    op.create_index("ix_categorization_rules_priority", "categorization_rules", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_categorization_rules_priority", table_name="categorization_rules")
    op.drop_table("categorization_rules")
