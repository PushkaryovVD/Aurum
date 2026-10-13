"""add confirmed Telegram transaction drafts

Revision ID: f9c3d5e7a012
Revises: f8b2c4d6e901
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f9c3d5e7a012"
down_revision: str | None = "f8b2c4d6e901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "telegram_transaction_drafts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("identity_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("workspace_id", uuid_type, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["identity_id"], ["telegram_identities.id"], name="fk_telegram_drafts_identity_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_transaction_drafts_identity_active",
        "telegram_transaction_drafts",
        ["identity_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_transaction_drafts_identity_active", table_name="telegram_transaction_drafts")
    op.drop_table("telegram_transaction_drafts")
