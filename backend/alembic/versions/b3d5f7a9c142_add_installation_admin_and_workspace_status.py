"""add installation administrators and blockable workspaces

Revision ID: b3d5f7a9c142
Revises: fa4d6e8b123
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b3d5f7a9c142"
down_revision: str | None = "fa4d6e8b123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

# Audit rows stay append-only, except that deleting a workspace may detach
# them from it (the FK's ON DELETE SET NULL), so the history outlives the space.
AUDIT_GUARD_WITH_WORKSPACE_DETACH = """
CREATE OR REPLACE FUNCTION aurum_reject_security_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.workspace_id IS NOT NULL
       AND NEW.workspace_id IS NULL
       AND NEW.id = OLD.id
       AND NEW.actor_user_id IS NOT DISTINCT FROM OLD.actor_user_id
       AND NEW.event_type = OLD.event_type
       AND NEW.outcome = OLD.outcome
       AND NEW.target_type IS NOT DISTINCT FROM OLD.target_type
       AND NEW.target_id IS NOT DISTINCT FROM OLD.target_id
       AND NEW.created_at = OLD.created_at THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'security audit events are append-only';
END;
$$
"""

AUDIT_GUARD_STRICT = """
CREATE OR REPLACE FUNCTION aurum_reject_security_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'security audit events are append-only';
END;
$$
"""


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workspaces",
        sa.Column("status", sa.String(length=10), nullable=False, server_default="active"),
    )
    op.add_column("workspaces", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_workspaces_status",
        "workspaces",
        "status IN ('active', 'blocked')",
    )
    op.execute(AUDIT_GUARD_WITH_WORKSPACE_DETACH)

    # The first owner (created by the one-time bootstrap) becomes the admin.
    op.execute(
        """
        UPDATE users SET is_admin = true
        WHERE id = (
            SELECT e.actor_user_id
            FROM security_audit_events e
            JOIN users u ON u.id = e.actor_user_id
            WHERE e.event_type = 'initial_owner_bootstrap'
              AND e.outcome = 'success'
              AND u.status = 'active'
            ORDER BY e.created_at, e.id
            LIMIT 1
        )
        """
    )
    # Without that audit trail, the earliest active user keeps the install manageable.
    op.execute(
        """
        UPDATE users SET is_admin = true
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE is_admin AND status = 'active')
          AND id = (
            SELECT id FROM users
            WHERE status = 'active'
            ORDER BY created_at, id
            LIMIT 1
          )
        """
    )


def downgrade() -> None:
    op.execute(AUDIT_GUARD_STRICT)
    op.drop_constraint("ck_workspaces_status", "workspaces", type_="check")
    op.drop_column("workspaces", "blocked_at")
    op.drop_column("workspaces", "status")
    op.drop_column("users", "is_admin")
