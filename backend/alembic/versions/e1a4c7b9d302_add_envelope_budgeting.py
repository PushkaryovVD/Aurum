"""add envelope budgeting

Creates isolated envelope planning/audit tables only. It does not modify account
balances or legacy budgets. Downgrade is structurally reversible but discards all
envelope data; export-before-downgrade cannot preserve envelope rows on restore.

Revision ID: e1a4c7b9d302
Revises: b7e2c4f19a35
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e1a4c7b9d302"
down_revision: str | None = "b7e2c4f19a35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "envelope_months",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_activity_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_envelope_month_year"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_envelope_month_number"),
        sa.UniqueConstraint("year", "month", name="uq_envelope_month"),
    )
    op.create_table(
        "envelope_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "envelope_template_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("envelope_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("rollover_positive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rollover_negative", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("planned_amount >= 0", name="ck_envelope_template_planned_nonnegative"),
        sa.UniqueConstraint("template_id", "category_id", name="uq_envelope_template_category"),
    )
    op.create_table(
        "envelope_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("rollover_positive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rollover_negative", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("assigned_amount >= 0", name="ck_envelope_assigned_nonnegative"),
        sa.CheckConstraint("planned_amount >= 0", name="ck_envelope_planned_nonnegative"),
        sa.UniqueConstraint("year", "month", "category_id", name="uq_envelope_month_category"),
    )
    op.create_index("ix_envelope_allocations_year_month", "envelope_allocations", ["year", "month"])
    op.create_table(
        "envelope_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_envelope_audit_logs_year_month", "envelope_audit_logs", ["year", "month"])


def downgrade() -> None:
    op.drop_index("ix_envelope_audit_logs_year_month", table_name="envelope_audit_logs")
    op.drop_table("envelope_audit_logs")
    op.drop_index("ix_envelope_allocations_year_month", table_name="envelope_allocations")
    op.drop_table("envelope_allocations")
    op.drop_table("envelope_template_items")
    op.drop_table("envelope_templates")
    op.drop_table("envelope_months")
