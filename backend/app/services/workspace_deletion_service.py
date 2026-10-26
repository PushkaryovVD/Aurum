"""Permanent removal of one household workspace and everything it owns.

The purge is derived from the ORM metadata instead of a hand-kept table
list, so a new financial table that carries ``workspace_id`` (or hangs off
one that does) is removed together with its workspace without touching this
module. Everything runs inside the caller's transaction: any failure leaves
the workspace exactly as it was.
"""
from uuid import UUID

from sqlalchemy import Table, delete, or_, select, update
from sqlalchemy.schema import sort_tables
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Base
from app.models.auth import SecurityAuditEvent, TelegramIdentity
from app.models.workspace import User, Workspace, WorkspaceKind

# Tables that reference a workspace but are not owned by it:
# - users / workspaces are identities, handled explicitly;
# - audit events are kept for accountability (workspace_id becomes NULL);
# - Telegram identities belong to a user and move to their personal space.
NOT_OWNED_BY_WORKSPACE = frozenset(
    {"users", "workspaces", "security_audit_events", "telegram_identities"}
)
# Following a SET NULL link would delete rows of *another* workspace that
# merely pointed here; the database nulls those references by itself.
_FOLLOWED_ON_DELETE = {None, "CASCADE", "RESTRICT", "NO ACTION"}


class WorkspaceDeletionRefused(Exception):
    """The workspace cannot be deleted (wrong kind or confirmation mismatch)."""


def _owned_rows(table: Table, workspace_id: UUID, memo: dict[str, ColumnElement | None]) -> ColumnElement | None:
    """Return a predicate selecting the rows of ``table`` owned by the workspace."""
    if table.name in memo:
        return memo[table.name]
    memo[table.name] = None  # guards against reference cycles
    if table.name in NOT_OWNED_BY_WORKSPACE:
        return None
    column = table.c.get("workspace_id")
    if column is not None and any(fk.column.table.name == "workspaces" for fk in column.foreign_keys):
        predicate: ColumnElement | None = column == workspace_id
    else:
        # A child without its own scope belongs to the workspace of its parent.
        clauses = []
        for fk in table.foreign_keys:
            parent = fk.column.table
            if parent is table or (fk.ondelete or None) not in _FOLLOWED_ON_DELETE:
                continue
            parent_predicate = _owned_rows(parent, workspace_id, memo)
            if parent_predicate is not None:
                clauses.append(fk.parent.in_(select(fk.column).where(parent_predicate)))
        predicate = or_(*clauses) if clauses else None
    memo[table.name] = predicate
    return predicate


def owned_tables(workspace_id: UUID) -> list[tuple[Table, ColumnElement]]:
    """Workspace-owned tables with their predicates, children before parents."""
    memo: dict[str, ColumnElement | None] = {}
    scoped = {
        table.name: (table, predicate)
        for table in Base.metadata.tables.values()
        if (predicate := _owned_rows(table, workspace_id, memo)) is not None
    }
    ordered = sort_tables([table for table, _ in scoped.values()])
    return [scoped[table.name] for table in reversed(ordered)]


async def purge_household_workspace(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    confirm_name: str,
) -> Workspace:
    """Delete one household workspace with its finances, memberships and invitations.

    The caller authorizes the actor and commits; audit history survives with
    ``workspace_id`` cleared so the record of the deletion itself stays intact.
    """
    workspace = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    ).scalar_one_or_none()
    if workspace is None:
        raise LookupError("workspace")
    if workspace.kind != WorkspaceKind.HOUSEHOLD:
        raise WorkspaceDeletionRefused("Personal workspaces cannot be deleted")
    if confirm_name.strip() != workspace.display_name.strip():
        raise WorkspaceDeletionRefused("Confirmation does not match the workspace name")

    # Telegram quick entry falls back to the owner's personal space.
    await session.execute(
        update(TelegramIdentity)
        .where(
            TelegramIdentity.default_workspace_id == workspace_id,
            TelegramIdentity.user_id == User.id,
            User.personal_workspace_id.is_not(None),
        )
        .values(default_workspace_id=User.personal_workspace_id, default_account_id=None)
        .execution_options(synchronize_session=False)
    )
    # A legacy identity without a personal space cannot keep pointing here.
    await session.execute(
        delete(TelegramIdentity)
        .where(TelegramIdentity.default_workspace_id == workspace_id)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(SecurityAuditEvent)
        .where(SecurityAuditEvent.workspace_id == workspace_id)
        .values(workspace_id=None)
        .execution_options(synchronize_session=False)
    )
    for table, predicate in owned_tables(workspace_id):
        await session.execute(delete(table).where(predicate))
    await session.execute(
        delete(Workspace).where(Workspace.id == workspace_id).execution_options(synchronize_session=False)
    )
    await session.flush()
    return workspace
