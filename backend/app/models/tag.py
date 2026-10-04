"""A free-form, reusable label on transactions — orthogonal to Category:
a category answers "what kind of spend is this", a tag answers "which
event/project does it belong to" (e.g. "trip:georgia", "tax-deductible").
A transaction can carry any number of tags, a tag can be reused across any
number of transactions — see transaction_tags below.
"""
from uuid import UUID as PythonUUID

from sqlalchemy import Column, ForeignKey, Index, String, Table, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column("transaction_id", ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    # Carries scope explicitly for review and future NOT NULL hardening.
    # The core-scope migration derives it from both parents on secondary
    # INSERTs and rejects mixed namespaces at the database boundary.
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True),
)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_tags_workspace_name"),
        Index("ix_tags_workspace_id_id", "workspace_id", "id"),
        Index("uq_tags_unscoped_name", "name", unique=True, postgresql_where=text("workspace_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable only for the temporary auth-disabled compatibility mode.
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(secondary=transaction_tags, back_populates="tags")
