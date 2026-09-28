"""merge asset depreciation and envelope budgeting heads

Revision ID: f0c9a4e1b672
Revises: c8d3e6f0a214, e1a4c7b9d302
"""
from collections.abc import Sequence

revision: str = "f0c9a4e1b672"
down_revision: tuple[str, str] = ("c8d3e6f0a214", "e1a4c7b9d302")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge independent feature histories without changing the schema."""


def downgrade() -> None:
    """Split history back to the two feature heads without changing the schema."""
