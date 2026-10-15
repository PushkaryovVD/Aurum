"""add Telegram quick-entry default account

Revision ID: fa4d6e8b123
Revises: f9c3d5e7a012
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "fa4d6e8b123"
down_revision: str | None = "f9c3d5e7a012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("telegram_identities", sa.Column("default_account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_telegram_identities_account_id_accounts",
        "telegram_identities",
        "accounts",
        ["default_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_telegram_identities_account_id_accounts",
        "telegram_identities",
        type_="foreignkey",
    )
    op.drop_column("telegram_identities", "default_account_id")
