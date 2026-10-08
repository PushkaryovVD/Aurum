"""scope envelope audit history and templates to workspaces

Audit rows and templates are financial records: leaving them global allows
same-month histories and category references from independent workspaces to
mix. Existing records are deliberately retained in the legacy NULL namespace.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE envelope_audit_logs, envelope_templates IN ACCESS EXCLUSIVE MODE")
    workspace_type = postgresql.UUID(as_uuid=True)
    for table in ("envelope_audit_logs", "envelope_templates"):
        op.add_column(table, sa.Column("workspace_id", workspace_type, nullable=True))
        op.create_foreign_key(
            f"fk_{table}_workspace_id_workspaces",
            table,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_index("ix_envelope_audit_logs_year_month", table_name="envelope_audit_logs")
    op.create_index(
        "ix_envelope_audit_logs_workspace_year_month_id",
        "envelope_audit_logs",
        ["workspace_id", "year", "month", "id"],
    )

    # The old global unique constraint prevents two workspaces from using the
    # same template name. The partial index preserves that exact guarantee for
    # old NULL-owned rows, while scoped rows are unique only within a workspace.
    op.drop_constraint("envelope_templates_name_key", "envelope_templates", type_="unique")
    op.create_index("ix_envelope_templates_workspace_id", "envelope_templates", ["workspace_id"])
    op.create_unique_constraint(
        "uq_envelope_templates_workspace_name",
        "envelope_templates",
        ["workspace_id", "name"],
    )
    op.create_index(
        "uq_envelope_templates_legacy_name",
        "envelope_templates",
        ["name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )

    op.execute(
        """
        CREATE FUNCTION protect_envelope_workspace_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'envelope workspace is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        """
    )
    for table in ("envelope_audit_logs", "envelope_templates"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable_workspace_scope "
            f"BEFORE UPDATE OF workspace_id ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_envelope_workspace_scope()"
        )


def downgrade() -> None:
    # The upgrade intentionally permits the same name in different workspaces.
    # Reverting to the old global constraint would merge those namespaces and
    # must never silently delete or rename user templates to make that happen.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM envelope_templates
            GROUP BY name
            HAVING COUNT(*) > 1
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade envelope template scope: duplicate names exist across workspaces'
              USING ERRCODE = '23514';
          END IF;
        END $$;
        """
    )
    for table in ("envelope_audit_logs", "envelope_templates"):
        op.execute(f"DROP TRIGGER {table}_immutable_workspace_scope ON {table}")
    op.execute("DROP FUNCTION protect_envelope_workspace_scope()")

    op.drop_index("uq_envelope_templates_legacy_name", table_name="envelope_templates")
    op.drop_constraint("uq_envelope_templates_workspace_name", "envelope_templates", type_="unique")
    op.drop_index("ix_envelope_templates_workspace_id", table_name="envelope_templates")
    op.create_unique_constraint("envelope_templates_name_key", "envelope_templates", ["name"])

    op.drop_index("ix_envelope_audit_logs_workspace_year_month_id", table_name="envelope_audit_logs")
    op.create_index("ix_envelope_audit_logs_year_month", "envelope_audit_logs", ["year", "month"])

    for table in ("envelope_audit_logs", "envelope_templates"):
        op.drop_constraint(f"fk_{table}_workspace_id_workspaces", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")
