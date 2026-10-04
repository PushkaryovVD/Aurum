"""Stage nullable workspace ownership for category budgets only.

Revision ID: e3b7c9d2a105
Revises: d2f6a8c1e940
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e3b7c9d2a105'
down_revision = 'd2f6a8c1e940'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Never guess a legacy budget's owner: existing budgets become NULL-scoped.
    # Lock before checking category compatibility to prevent concurrent writes
    # between the fail-closed check and schema changes. Correct this blocking
    # revision in place; a later migration cannot repair a failed upgrade here.
    op.execute('LOCK TABLE categories, budgets IN ACCESS EXCLUSIVE MODE')
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM budgets b JOIN categories c ON c.id = b.category_id
                     WHERE c.workspace_id IS NOT NULL) THEN
            RAISE EXCEPTION 'budget category workspace mismatch' USING ERRCODE = '23514';
          END IF;
        END $$;
    """)
    op.add_column('budgets', sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_budgets_workspace_id_workspaces', 'budgets', 'workspaces', ['workspace_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_budgets_workspace_id_id', 'budgets', ['workspace_id', 'id'])
    op.drop_constraint('uq_budgets_category_id', 'budgets', type_='unique')
    op.create_unique_constraint('uq_budgets_workspace_category', 'budgets', ['workspace_id', 'category_id'])
    # NULL remains the auth-disabled namespace and must also be unique.
    op.create_index('uq_budgets_unscoped_category', 'budgets', ['category_id'], unique=True, postgresql_where=sa.text('workspace_id IS NULL'))

    # A normal nullable composite FK would skip NULL namespaces. Compare
    # explicitly, locking the category against concurrent mutation/deletion.
    op.execute("""
        CREATE FUNCTION enforce_budget_category_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE category_scope uuid;
        BEGIN
          SELECT workspace_id INTO category_scope FROM categories
            WHERE id = NEW.category_id FOR SHARE;
          IF FOUND AND NEW.workspace_id IS DISTINCT FROM category_scope THEN
            RAISE EXCEPTION 'budget category workspace mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("CREATE TRIGGER budgets_category_scope BEFORE INSERT OR UPDATE ON budgets "
               "FOR EACH ROW EXECUTE FUNCTION enforce_budget_category_scope()")
    # Ownership transfer is deliberately unavailable in this staged slice.
    # Immutability closes parent-update races even at snapshot isolation,
    # without replacing any of the existing core-scope triggers/functions.
    op.execute("""
        CREATE FUNCTION protect_budget_category_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'budget/category workspace is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in ('categories', 'budgets'):
        op.execute(f"CREATE TRIGGER {table}_budget_immutable_scope BEFORE UPDATE OF workspace_id ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION protect_budget_category_scope()")


def downgrade() -> None:
    for table in ('categories', 'budgets'):
        op.execute(f"DROP TRIGGER {table}_budget_immutable_scope ON {table}")
    op.execute('DROP FUNCTION protect_budget_category_scope()')
    op.execute('DROP TRIGGER budgets_category_scope ON budgets')
    op.execute('DROP FUNCTION enforce_budget_category_scope()')
    op.drop_index('uq_budgets_unscoped_category', table_name='budgets')
    op.drop_constraint('uq_budgets_workspace_category', 'budgets', type_='unique')
    op.create_unique_constraint('uq_budgets_category_id', 'budgets', ['category_id'])
    op.drop_index('ix_budgets_workspace_id_id', table_name='budgets')
    op.drop_constraint('fk_budgets_workspace_id_workspaces', 'budgets', type_='foreignkey')
    op.drop_column('budgets', 'workspace_id')
