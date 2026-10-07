"""Monthly zero-based envelopes, separate from accounts and legacy budgets."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID as PythonUUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class EnvelopeMonth(Base, TimestampMixin):
    __tablename__ = "envelope_months"
    __table_args__ = (
        UniqueConstraint("workspace_id", "year", "month", name="uq_envelope_month_workspace"),
        Index("ix_envelope_months_workspace_id", "workspace_id"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_envelope_month_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_envelope_month_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable only for the temporary auth-disabled compatibility mode.
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_activity_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class EnvelopeAllocation(Base, TimestampMixin):
    __tablename__ = "envelope_allocations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "year", "month", "category_id",
            name="uq_envelope_month_category_workspace",
        ),
        CheckConstraint("assigned_amount >= 0", name="ck_envelope_assigned_nonnegative"),
        CheckConstraint("planned_amount >= 0", name="ck_envelope_planned_nonnegative"),
        Index("ix_envelope_allocations_year_month", "year", "month"),
        Index("ix_envelope_allocations_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable only for the temporary auth-disabled compatibility mode.
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    assigned_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    rollover_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    rollover_negative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class EnvelopeAuditLog(Base):
    """Append-only history. Core bulk deletes are reserved for backup restore."""
    __tablename__ = "envelope_audit_logs"
    __table_args__ = (Index("ix_envelope_audit_logs_year_month", "year", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    from_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    to_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


@event.listens_for(EnvelopeAuditLog, "before_update")
@event.listens_for(EnvelopeAuditLog, "before_delete")
def _prevent_audit_mutation(*_args: object) -> None:
    # Backup restore intentionally uses SQLAlchemy Core bulk delete, which bypasses mapper events.
    raise RuntimeError("Envelope audit history is immutable")


class EnvelopeTemplate(Base, TimestampMixin):
    __tablename__ = "envelope_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class EnvelopeTemplateItem(Base):
    __tablename__ = "envelope_template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "category_id", name="uq_envelope_template_category"),
        CheckConstraint("planned_amount >= 0", name="ck_envelope_template_planned_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("envelope_templates.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    rollover_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    rollover_negative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
