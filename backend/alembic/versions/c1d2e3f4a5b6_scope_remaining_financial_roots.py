"""stage nullable workspace ownership for the remaining financial roots

Adds a nullable ``workspace_id`` to the root financial tables that still lack
one so an authenticated request can be scoped to its workspace. Child tables
(asset_valuations, goal_contributions, crypto_holdings, securities, trades,
dividends, prices, envelope_audit_logs) derive their scope from their root and
are deliberately left alone: filtering is done through the root join, which
keeps one authoritative owner per row.

Populated legacy rows stay in the ``NULL`` namespace and are never re-owned.

Revision ID: c1d2e3f4a5b6
Revises: f7a1c2d3e406
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "f7a1c2d3e406"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Root tables that gain their own ownership. Everything hanging off these
# (valuations, contributions, holdings, securities, trades, prices) is scoped
# through its root instead of carrying a second copy of the same fact.
_ROOT_TABLES = (
    "assets",
    "goals",
    "recurring_transactions",
    "crypto_portfolios",
    "investment_portfolios",
    "categorization_rules",
    "envelope_months",
    "envelope_allocations",
)

_INDEXED_ROOTS = (
    "assets",
    "goals",
    "recurring_transactions",
    "crypto_portfolios",
    "investment_portfolios",
    "categorization_rules",
)


def upgrade() -> None:
    # Lock before the additive change so a concurrent legacy write cannot race
    # the constraint replacement below. Correct this revision in place; a later
    # migration cannot run when an upgrade is blocked here.
    op.execute(
        "LOCK TABLE assets, goals, recurring_transactions, crypto_portfolios, "
        "investment_portfolios, categorization_rules, envelope_months, "
        "envelope_allocations IN ACCESS EXCLUSIVE MODE"
    )

    workspace_type = postgresql.UUID(as_uuid=True)
    for table in _ROOT_TABLES:
        op.add_column(table, sa.Column("workspace_id", workspace_type, nullable=True))
        op.create_foreign_key(
            f"fk_{table}_workspace_id_workspaces",
            table,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    for table in _INDEXED_ROOTS:
        op.create_index(f"ix_{table}_workspace_id_id", table, ["workspace_id", "id"])
    op.create_index("ix_envelope_months_workspace_id", "envelope_months", ["workspace_id"])
    op.create_index(
        "ix_envelope_allocations_workspace_id", "envelope_allocations", ["workspace_id"]
    )

    # Envelope months and allocations were globally unique. They become unique
    # per workspace, and the legacy NULL namespace keeps its own uniqueness
    # through a partial index (a nullable-leading UNIQUE does not do that).
    op.drop_constraint("uq_envelope_month", "envelope_months", type_="unique")
    op.create_unique_constraint(
        "uq_envelope_month_workspace", "envelope_months", ["workspace_id", "year", "month"]
    )
    op.create_index(
        "uq_envelope_month_unscoped",
        "envelope_months",
        ["year", "month"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )

    op.drop_constraint("uq_envelope_month_category", "envelope_allocations", type_="unique")
    op.create_unique_constraint(
        "uq_envelope_month_category_workspace",
        "envelope_allocations",
        ["workspace_id", "year", "month", "category_id"],
    )
    op.create_index(
        "uq_envelope_month_category_unscoped",
        "envelope_allocations",
        ["year", "month", "category_id"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )

    # Ownership transfer is deliberately unavailable in this staged slice.
    # Immutability closes parent-update races at every isolation level without
    # replacing any existing scope trigger.
    op.execute(
        """
        CREATE FUNCTION protect_financial_root_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'financial workspace is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """
    )
    for table in _ROOT_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable_scope BEFORE UPDATE OF workspace_id ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_financial_root_scope()"
        )


def downgrade() -> None:
    for table in _ROOT_TABLES:
        op.execute(f"DROP TRIGGER {table}_immutable_scope ON {table}")
    op.execute("DROP FUNCTION protect_financial_root_scope()")

    op.drop_index("uq_envelope_month_category_unscoped", table_name="envelope_allocations")
    op.drop_constraint(
        "uq_envelope_month_category_workspace", "envelope_allocations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_envelope_month_category",
        "envelope_allocations",
        ["year", "month", "category_id"],
    )

    op.drop_index("uq_envelope_month_unscoped", table_name="envelope_months")
    op.drop_constraint("uq_envelope_month_workspace", "envelope_months", type_="unique")
    op.create_unique_constraint("uq_envelope_month", "envelope_months", ["year", "month"])

    op.drop_index("ix_envelope_allocations_workspace_id", table_name="envelope_allocations")
    op.drop_index("ix_envelope_months_workspace_id", table_name="envelope_months")
    for table in _INDEXED_ROOTS:
        op.drop_index(f"ix_{table}_workspace_id_id", table_name=table)

    for table in _ROOT_TABLES:
        op.drop_constraint(f"fk_{table}_workspace_id_workspaces", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")