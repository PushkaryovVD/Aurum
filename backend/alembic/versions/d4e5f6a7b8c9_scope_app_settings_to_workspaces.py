"""scope app settings to workspaces without re-owning legacy settings

Existing ``app_settings`` rows remain in the NULL compatibility namespace.
Authenticated workspaces receive independent rows created during their
transactional bootstrap; no legacy setting is deleted, updated, or assigned.

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The table is normally a singleton, but preserve every historical row
    # byte-for-byte in the legacy NULL namespace while adding scoped rows.
    op.execute("LOCK TABLE app_settings IN ACCESS EXCLUSIVE MODE")
    op.add_column("app_settings", sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_app_settings_workspace_id_workspaces",
        "app_settings",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_app_settings_workspace_id", "app_settings", ["workspace_id"])
    op.create_index(
        "uq_app_settings_workspace_id",
        "app_settings",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    # Legacy startup code inserted id=1 explicitly, which does not advance
    # PostgreSQL's sequence. Advance it before scoped rows rely on generated
    # IDs, without touching any legacy record.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('app_settings', 'id'), "
        "GREATEST(COALESCE((SELECT MAX(id) FROM app_settings), 1), 1), true)"
    )

    op.execute(
        """
        CREATE FUNCTION protect_app_settings_workspace_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'settings workspace is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER app_settings_immutable_workspace_scope "
        "BEFORE UPDATE OF workspace_id ON app_settings "
        "FOR EACH ROW EXECUTE FUNCTION protect_app_settings_workspace_scope()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER app_settings_immutable_workspace_scope ON app_settings")
    op.execute("DROP FUNCTION protect_app_settings_workspace_scope()")
    op.drop_index("uq_app_settings_workspace_id", table_name="app_settings")
    op.drop_index("ix_app_settings_workspace_id", table_name="app_settings")
    op.drop_constraint("fk_app_settings_workspace_id_workspaces", "app_settings", type_="foreignkey")
    op.drop_column("app_settings", "workspace_id")
