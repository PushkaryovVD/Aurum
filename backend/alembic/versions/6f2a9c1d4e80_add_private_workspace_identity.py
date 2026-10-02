"""add private workspace identity foundation

Revision ID: 6f2a9c1d4e80
Revises: f0c9a4e1b672
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "6f2a9c1d4e80"
down_revision: str | None = "f0c9a4e1b672"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATEMENT_BREAK = "-- aurum migration statement break"


def _execute_ddl_batch(ddl: str) -> None:
    """Execute complete PostgreSQL DDL statements one at a time.

    The asyncpg dialect prepares every ``op.execute`` payload, and PostgreSQL
    rejects a prepared payload containing several top-level statements.  The
    PL/pgSQL bodies still contain semicolons, so explicit separators are safer
    than attempting to split SQL on semicolons.
    """
    for statement in ddl.split(_STATEMENT_BREAK):
        op.execute(statement)


INVARIANT_FUNCTIONS = """
CREATE FUNCTION aurum_assert_user_personal_workspace(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_status varchar(10);
    v_workspace_id uuid;
    v_match_count integer;
BEGIN
    SELECT status, personal_workspace_id
      INTO v_status, v_workspace_id
      FROM users
     WHERE id = p_user_id
     FOR UPDATE;

    IF NOT FOUND OR v_status <> 'active' THEN
        RETURN;
    END IF;

    IF v_workspace_id IS NULL THEN
        RAISE EXCEPTION 'active user must have exactly one personal workspace';
    END IF;

    SELECT count(*)
      INTO v_match_count
      FROM workspaces w
     WHERE w.id = v_workspace_id
       AND w.kind = 'personal'
       AND w.personal_owner_user_id = p_user_id;

    IF v_match_count <> 1 THEN
        RAISE EXCEPTION 'active user must have exactly one personal workspace';
    END IF;

    SELECT count(*)
      INTO v_match_count
      FROM workspace_memberships m
     WHERE m.workspace_id = v_workspace_id
       AND m.user_id = p_user_id
       AND m.role = 'owner'
       AND m.revoked_at IS NULL;

    IF v_match_count <> 1 THEN
        RAISE EXCEPTION 'active user must have exactly one personal workspace';
    END IF;
END;
$$;
-- aurum migration statement break

CREATE FUNCTION aurum_assert_workspace_membership(p_workspace_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_kind varchar(10);
    v_owner_id uuid;
    v_active_count integer;
    v_matching_count integer;
BEGIN
    SELECT kind, personal_owner_user_id
      INTO v_kind, v_owner_id
      FROM workspaces
     WHERE id = p_workspace_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_kind = 'personal' THEN
        SELECT count(*),
               count(*) FILTER (
                   WHERE user_id = v_owner_id AND role = 'owner'
               )
          INTO v_active_count, v_matching_count
          FROM workspace_memberships
         WHERE workspace_id = p_workspace_id
           AND revoked_at IS NULL;

        IF v_active_count <> 1 OR v_matching_count <> 1 THEN
            RAISE EXCEPTION 'personal workspace must have exactly one active owner membership';
        END IF;

        SELECT count(*)
          INTO v_matching_count
          FROM users
         WHERE id = v_owner_id
           AND personal_workspace_id = p_workspace_id;

        IF v_matching_count <> 1 THEN
            RAISE EXCEPTION 'personal workspace owner must point back to the workspace';
        END IF;
    ELSE
        SELECT count(*)
          INTO v_matching_count
          FROM workspace_memberships
         WHERE workspace_id = p_workspace_id
           AND role = 'owner'
           AND revoked_at IS NULL;

        IF v_matching_count < 1 THEN
            RAISE EXCEPTION 'household workspace must have an active owner';
        END IF;
    END IF;
END;
$$;
-- aurum migration statement break

CREATE FUNCTION aurum_validate_workspace_invariants()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'users' THEN
        PERFORM aurum_assert_user_personal_workspace(COALESCE(NEW.id, OLD.id));
    ELSIF TG_TABLE_NAME = 'workspaces' THEN
        IF TG_OP <> 'INSERT' THEN
            PERFORM aurum_assert_workspace_membership(OLD.id);
            IF OLD.personal_owner_user_id IS NOT NULL THEN
                PERFORM aurum_assert_user_personal_workspace(OLD.personal_owner_user_id);
            END IF;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            PERFORM aurum_assert_workspace_membership(NEW.id);
            IF NEW.personal_owner_user_id IS NOT NULL THEN
                PERFORM aurum_assert_user_personal_workspace(NEW.personal_owner_user_id);
            END IF;
        END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN
            PERFORM aurum_assert_workspace_membership(OLD.workspace_id);
            PERFORM aurum_assert_user_personal_workspace(OLD.user_id);
        END IF;
        IF TG_OP <> 'DELETE' THEN
            PERFORM aurum_assert_workspace_membership(NEW.workspace_id);
            PERFORM aurum_assert_user_personal_workspace(NEW.user_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;
-- aurum migration statement break

CREATE FUNCTION aurum_reject_workspace_identity_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.personal_owner_user_id IS DISTINCT FROM OLD.personal_owner_user_id THEN
        RAISE EXCEPTION 'personal workspace kind and owner are immutable';
    END IF;
    RETURN NEW;
END;
$$;
-- aurum migration statement break

CREATE FUNCTION aurum_reject_personal_workspace_pointer_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.personal_workspace_id IS NOT NULL
       AND NEW.personal_workspace_id IS DISTINCT FROM OLD.personal_workspace_id THEN
        RAISE EXCEPTION 'personal workspace pointer is immutable';
    END IF;
    RETURN NEW;
END;
$$;
"""


TRIGGERS = """
CREATE TRIGGER users_personal_workspace_immutable
BEFORE UPDATE OF personal_workspace_id ON users
FOR EACH ROW EXECUTE FUNCTION aurum_reject_personal_workspace_pointer_change();
-- aurum migration statement break

CREATE TRIGGER workspaces_identity_immutable
BEFORE UPDATE OF kind, personal_owner_user_id ON workspaces
FOR EACH ROW EXECUTE FUNCTION aurum_reject_workspace_identity_change();
-- aurum migration statement break

CREATE CONSTRAINT TRIGGER users_workspace_invariants
AFTER INSERT OR UPDATE OR DELETE ON users
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION aurum_validate_workspace_invariants();
-- aurum migration statement break

CREATE CONSTRAINT TRIGGER workspaces_membership_invariants
AFTER INSERT OR UPDATE OR DELETE ON workspaces
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION aurum_validate_workspace_invariants();
-- aurum migration statement break

CREATE CONSTRAINT TRIGGER memberships_workspace_invariants
AFTER INSERT OR UPDATE OR DELETE ON workspace_memberships
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION aurum_validate_workspace_invariants();
"""


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("normalized_login", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("personal_workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        sa.UniqueConstraint("normalized_login", name="uq_users_normalized_login"),
        sa.UniqueConstraint(
            "personal_workspace_id",
            name="uq_users_personal_workspace_id",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("personal_owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('personal', 'household')", name="ck_workspaces_kind"),
        sa.CheckConstraint(
            "(kind = 'personal' AND personal_owner_user_id IS NOT NULL) "
            "OR (kind = 'household' AND personal_owner_user_id IS NULL)",
            name="ck_workspaces_personal_owner_matches_kind",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_workspaces_created_by_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["personal_owner_user_id"],
            ["users.id"],
            name="fk_workspaces_personal_owner_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        "uq_workspaces_personal_owner",
        "workspaces",
        ["personal_owner_user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'personal'"),
    )
    op.create_foreign_key(
        "fk_users_personal_workspace_id_workspaces",
        "users",
        "workspaces",
        ["personal_workspace_id"],
        ["id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_workspace_memberships_role"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_memberships_workspace_id_workspaces",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_workspace_memberships_user_id_users",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
    op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])
    op.create_index(
        "uq_workspace_memberships_active_user",
        "workspace_memberships",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    _execute_ddl_batch(INVARIANT_FUNCTIONS)
    _execute_ddl_batch(TRIGGERS)


def downgrade() -> None:
    op.execute("DROP TRIGGER memberships_workspace_invariants ON workspace_memberships")
    op.execute("DROP TRIGGER workspaces_membership_invariants ON workspaces")
    op.execute("DROP TRIGGER users_workspace_invariants ON users")
    op.execute("DROP TRIGGER workspaces_identity_immutable ON workspaces")
    op.execute("DROP TRIGGER users_personal_workspace_immutable ON users")
    op.execute("DROP FUNCTION aurum_validate_workspace_invariants()")
    op.execute("DROP FUNCTION aurum_assert_workspace_membership(uuid)")
    op.execute("DROP FUNCTION aurum_assert_user_personal_workspace(uuid)")
    op.execute("DROP FUNCTION aurum_reject_workspace_identity_change()")
    op.execute("DROP FUNCTION aurum_reject_personal_workspace_pointer_change()")
    op.drop_index("uq_workspace_memberships_active_user", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_constraint("fk_users_personal_workspace_id_workspaces", "users", type_="foreignkey")
    op.drop_index("uq_workspaces_personal_owner", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_table("users")
