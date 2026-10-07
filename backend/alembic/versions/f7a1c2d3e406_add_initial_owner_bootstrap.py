"""add one-time initial owner bootstrap state

Revision ID: f7a1c2d3e406
Revises: e3b7c9d2a105
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f7a1c2d3e406"
down_revision: str | None = "e3b7c9d2a105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_auth_rate_limits_purpose_window",
        "auth_rate_limits",
        ["purpose", "window_started_at"],
        unique=False,
    )
    op.create_table(
        "initial_owner_bootstrap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hmac", sa.LargeBinary(32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_initial_owner_bootstrap_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("initial_owner_bootstrap")
    op.drop_index("ix_auth_rate_limits_purpose_window", table_name="auth_rate_limits")