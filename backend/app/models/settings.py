"""Per-workspace financial display and alert configuration.

``workspace_id IS NULL`` remains the preserved legacy/auth-disabled singleton
namespace (id=1); authenticated workspaces each have one scoped row.
"""
from decimal import Decimal
from uuid import UUID as PythonUUID

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        Index("ix_app_settings_workspace_id", "workspace_id"),
        Index(
            "uq_app_settings_workspace_id",
            "workspace_id",
            unique=True,
            postgresql_where=text("workspace_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Consecutive complete months of negative cash flow / declining net worth
    # before insights_service.py raises the corresponding alert.
    negative_cash_flow_threshold_months: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    net_worth_decline_threshold_months: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    # Max % of total capital (cash + assets) allowed in medium/high risk
    # tiers before insights_service.py raises risky_allocation_exceeded —
    # the classic "80% at zero risk, 20% at most exposed" rule.
    risky_allocation_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    # A depository account (checking/savings/cash) sitting at or above this
    # balance with no transaction touching it in idle_cash_threshold_days
    # raises insights_service.py's idle_cash alert — money that isn't
    # working. In the app's display currency (see `currency` above).
    idle_cash_threshold_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("1000"))
    idle_cash_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
