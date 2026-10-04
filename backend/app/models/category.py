"""A spending/income category, colored so it maps 1:1 to a dashboard chart slot."""
from uuid import UUID as PythonUUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CategoryKind


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (Index("ix_categories_workspace_id_id", "workspace_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable only for the temporary auth-disabled compatibility mode.
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, name="category_kind", native_enum=False, length=10), nullable=False
    )
    # Lucide icon name rendered in the frontend (kept as a plain string so new
    # icons don't require a migration).
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Hex color drawn from the dataviz skill's validated categorical palette.
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # Fixed slot ordering keeps the donut chart's category order stable across renders.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Self-referential, one level deep only (routes/categories.py rejects a
    # parent that itself has a parent) — a subcategory ("Alcohol" under
    # "Groceries"). SET NULL so deleting a parent turns its children back
    # into top-level categories instead of cascading the delete.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
