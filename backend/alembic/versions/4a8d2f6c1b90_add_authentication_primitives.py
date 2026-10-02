"""add authentication persistence primitives

Revision ID: 4a8d2f6c1b90
Revises: 6f2a9c1d4e80
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4a8d2f6c1b90"
down_revision: str | None = "6f2a9c1d4e80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(512), nullable=False))

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hmac", sa.LargeBinary(32), nullable=False),
        sa.Column("csrf_secret", sa.LargeBinary(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_ip_hmac", sa.LargeBinary(32), nullable=True),
        sa.Column("user_agent_hmac", sa.LargeBinary(32), nullable=True),
        sa.CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_user_sessions_expiry_order"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hmac", name="uq_user_sessions_token_hmac"),
    )
    op.create_index("ix_user_sessions_user_id_active", "user_sessions", ["user_id", "revoked_at"])

    op.create_table(
        "auth_rate_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("bucket_hmac", sa.LargeBinary(32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempt_count >= 0", name="ck_auth_rate_limits_attempt_count"),
        sa.UniqueConstraint("purpose", "bucket_hmac", name="uq_auth_rate_limits_purpose_bucket"),
    )

    op.create_table(
        "security_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_security_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_security_audit_events_workspace_id_workspaces",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_security_audit_events_actor_created",
        "security_audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_security_audit_events_workspace_created",
        "security_audit_events",
        ["workspace_id", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION aurum_reject_security_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'security audit events are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER security_audit_events_append_only
        BEFORE UPDATE OR DELETE ON security_audit_events
        FOR EACH ROW EXECUTE FUNCTION aurum_reject_security_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER security_audit_events_append_only ON security_audit_events")
    op.execute("DROP FUNCTION aurum_reject_security_audit_mutation()")
    op.drop_index("ix_security_audit_events_workspace_created", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_actor_created", table_name="security_audit_events")
    op.drop_table("security_audit_events")
    op.drop_table("auth_rate_limits")
    op.drop_index("ix_user_sessions_user_id_active", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_column("users", "password_hash")
