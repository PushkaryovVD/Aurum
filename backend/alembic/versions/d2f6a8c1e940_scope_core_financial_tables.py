"""stage nullable workspace ownership for core financial tables

Revision ID: d2f6a8c1e940
Revises: 9c4e2b7d1a60
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d2f6a8c1e940"
down_revision: str | None = "9c4e2b7d1a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CORE_TABLES = (
    "transaction_tags",
    "transaction_splits",
    "transactions",
    "tags",
    "categories",
    "accounts",
)


def upgrade() -> None:
    # Populated legacy rows remain in the NULL namespace; never invent owners.
    # Lock before the additive changes so concurrent legacy writes cannot race
    # index/constraint replacement. This earlier revision must be corrected:
    # a later repair cannot run when an upgrade is blocked here.
    op.execute("LOCK TABLE accounts, categories, tags, transactions, transaction_splits, transaction_tags IN ACCESS EXCLUSIVE MODE")

    workspace_type = postgresql.UUID(as_uuid=True)
    for table in ("accounts", "categories", "tags", "transactions", "transaction_splits", "transaction_tags"):
        op.add_column(table, sa.Column("workspace_id", workspace_type, nullable=True))
        op.create_foreign_key(
            f"fk_{table}_workspace_id_workspaces",
            table,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.add_column("transactions", sa.Column("author_user_id", workspace_type, nullable=True))
    op.create_foreign_key(
        "fk_transactions_author_user_id_users",
        "transactions",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index("ix_accounts_workspace_id_id", "accounts", ["workspace_id", "id"])
    op.create_index("ix_categories_workspace_id_id", "categories", ["workspace_id", "id"])
    op.create_index("ix_tags_workspace_id_id", "tags", ["workspace_id", "id"])
    op.create_index("ix_transactions_workspace_id_id", "transactions", ["workspace_id", "id"])
    op.create_index("ix_transaction_splits_workspace_id", "transaction_splits", ["workspace_id"])
    op.create_index("ix_transaction_tags_workspace_id", "transaction_tags", ["workspace_id"])

    op.drop_constraint("tags_name_key", "tags", type_="unique")
    op.create_unique_constraint("uq_tags_workspace_name", "tags", ["workspace_id", "name"])
    op.drop_constraint("uq_transaction_account_external_id", "transactions", type_="unique")
    op.create_unique_constraint(
        "uq_transaction_workspace_account_external_id",
        "transactions",
        ["workspace_id", "account_id", "external_id"],
    )

    # NULL workspace is the legacy namespace; ordinary nullable-leading
    # UNIQUE constraints do not preserve its historical uniqueness.
    op.create_index("uq_tags_unscoped_name", "tags", ["name"], unique=True,
                    postgresql_where=sa.text("workspace_id IS NULL"))
    op.create_index("uq_transactions_unscoped_account_external_id", "transactions",
                    ["account_id", "external_id"], unique=True,
                    postgresql_where=sa.text("workspace_id IS NULL"))

    # Secondary ORM inserts supply only the two IDs. Derive scope in the DB,
    # reject mixed namespaces (including NULL vs scoped), and lock parents
    # against concurrent re-scoping until the association write commits.
    op.execute("""
        CREATE FUNCTION enforce_transaction_tag_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE transaction_scope uuid; tag_scope uuid;
        BEGIN
          SELECT workspace_id INTO transaction_scope FROM transactions
            WHERE id = NEW.transaction_id FOR SHARE;
          SELECT workspace_id INTO tag_scope FROM tags
            WHERE id = NEW.tag_id FOR SHARE;
          IF transaction_scope IS DISTINCT FROM tag_scope OR
             (NEW.workspace_id IS NOT NULL AND NEW.workspace_id IS DISTINCT FROM transaction_scope) THEN
            RAISE EXCEPTION 'transaction tag workspace mismatch' USING ERRCODE = '23514';
          END IF;
          NEW.workspace_id := transaction_scope;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER transaction_tags_scope BEFORE INSERT OR UPDATE ON transaction_tags
        FOR EACH ROW EXECUTE FUNCTION enforce_transaction_tag_scope();
    """)

    # This compatibility release has no ownership-transfer/backfill path.
    # Immutable parent scope closes UPDATE races at every isolation level,
    # including snapshots that cannot see a concurrently committed link.
    op.execute("""
        CREATE FUNCTION protect_transaction_tag_parent_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'transaction/tag workspace is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in ("transactions", "tags"):
        op.execute(f"CREATE TRIGGER {table}_immutable_scope BEFORE UPDATE OF workspace_id ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION protect_transaction_tag_parent_scope()")


def downgrade() -> None:
    for table in ("transactions", "tags"):
        op.execute(f"DROP TRIGGER {table}_immutable_scope ON {table}")
    op.execute("DROP FUNCTION protect_transaction_tag_parent_scope()")

    op.execute("DROP TRIGGER transaction_tags_scope ON transaction_tags")
    op.execute("DROP FUNCTION enforce_transaction_tag_scope()")
    op.drop_index("uq_transactions_unscoped_account_external_id", table_name="transactions")
    op.drop_index("uq_tags_unscoped_name", table_name="tags")
    op.drop_constraint("uq_transaction_workspace_account_external_id", "transactions", type_="unique")
    op.create_unique_constraint("uq_transaction_account_external_id", "transactions", ["account_id", "external_id"])
    op.drop_constraint("uq_tags_workspace_name", "tags", type_="unique")
    op.create_unique_constraint("tags_name_key", "tags", ["name"])

    op.drop_index("ix_transaction_tags_workspace_id", table_name="transaction_tags")
    op.drop_index("ix_transaction_splits_workspace_id", table_name="transaction_splits")
    op.drop_index("ix_transactions_workspace_id_id", table_name="transactions")
    op.drop_index("ix_tags_workspace_id_id", table_name="tags")
    op.drop_index("ix_categories_workspace_id_id", table_name="categories")
    op.drop_index("ix_accounts_workspace_id_id", table_name="accounts")

    op.drop_constraint("fk_transactions_author_user_id_users", "transactions", type_="foreignkey")
    op.drop_column("transactions", "author_user_id")
    for table in _CORE_TABLES:
        op.drop_constraint(f"fk_{table}_workspace_id_workspaces", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")
