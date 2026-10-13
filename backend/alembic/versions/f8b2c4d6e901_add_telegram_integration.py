"""add Telegram identities and one-time link codes

Revision ID: f8b2c4d6e901
Revises: e5f6a7b8c9d0
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f8b2c4d6e901"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "telegram_identities",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("default_workspace_id", uuid_type, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_telegram_identities_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_workspace_id"], ["workspaces.id"], name="fk_telegram_identities_workspace_id_workspaces", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_telegram_identities_user_id"),
        sa.UniqueConstraint("telegram_user_id", name="uq_telegram_identities_telegram_user_id"),
    )
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("workspace_id", uuid_type, nullable=False),
        sa.Column("code_hmac", sa.LargeBinary(length=32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_telegram_link_codes_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_telegram_link_codes_workspace_id_workspaces", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hmac", name="uq_telegram_link_codes_code_hmac"),
    )
    op.create_index(
        "ix_telegram_link_codes_user_active",
        "telegram_link_codes",
        ["user_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_link_codes_user_active", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_table("telegram_identities")
