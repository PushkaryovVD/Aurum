"""A monthly spending limit for one expense category — compared against
actual spend for whichever month is being viewed (services/budget_service.py).
Not month-scoped itself: one limit per category, in effect until changed."""
from decimal import Decimal

from uuid import UUID as PythonUUID

from sqlalchemy import ForeignKey, Index, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "category_id", name="uq_budgets_workspace_category"),
        Index("ix_budgets_workspace_id_id", "workspace_id", "id"),
        Index("uq_budgets_unscoped_category", "category_id", unique=True,
              postgresql_where=text("workspace_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable only for the staged auth-disabled compatibility namespace.
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    category: Mapped["Category"] = relationship()
