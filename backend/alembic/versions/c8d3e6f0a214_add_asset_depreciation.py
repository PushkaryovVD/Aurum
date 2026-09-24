"""add asset depreciation and revaluation metadata

Revision ID: c8d3e6f0a214
Revises: b7e2c4f19a35
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c8d3e6f0a214"
down_revision: str | None = "b7e2c4f19a35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("acquisition_date", sa.Date(), nullable=True))
    op.add_column("assets", sa.Column("acquisition_cost", sa.Numeric(14, 2), nullable=True))
    op.add_column("assets", sa.Column("residual_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("assets", sa.Column("valuation_mode", sa.Enum("MANUAL_ONLY", "STRAIGHT_LINE", "ANNUAL_PERCENTAGE", name="asset_valuation_mode", native_enum=False, length=20), nullable=False, server_default="MANUAL_ONLY"))
    op.add_column("assets", sa.Column("useful_life_years", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("annual_depreciation_rate", sa.Numeric(7, 4), nullable=True))
    op.alter_column("assets", "valuation_mode", server_default=None)
    op.create_check_constraint(
        "ck_assets_depreciation_inputs",
        "assets",
        "valuation_mode = 'MANUAL_ONLY' OR ("
        "acquisition_date IS NOT NULL AND acquisition_cost IS NOT NULL AND acquisition_cost >= 0 "
        "AND (residual_value IS NULL OR (residual_value >= 0 AND residual_value <= acquisition_cost)) "
        "AND (valuation_mode <> 'STRAIGHT_LINE' OR (useful_life_years IS NOT NULL AND useful_life_years BETWEEN 1 AND 100)) "
        "AND (valuation_mode <> 'ANNUAL_PERCENTAGE' OR (annual_depreciation_rate IS NOT NULL AND annual_depreciation_rate > 0 AND annual_depreciation_rate < 100))"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_assets_depreciation_inputs", "assets", type_="check")
    op.drop_column("assets", "annual_depreciation_rate")
    op.drop_column("assets", "useful_life_years")
    op.drop_column("assets", "valuation_mode")
    op.drop_column("assets", "residual_value")
    op.drop_column("assets", "acquisition_cost")
    op.drop_column("assets", "acquisition_date")