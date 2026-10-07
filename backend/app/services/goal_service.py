"""Savings goals: CRUD for the goal itself, plus a running current_amount —
the sum of all logged GoalContribution rows, computed on read rather than
stored, so it's never out of sync with the log.

Every read and write is scoped to the request workspace. GoalContribution has
no workspace_id of its own, so it is always reached (and written) through its
parent Goal, which is itself resolved through the scope filter — a foreign
goal id can therefore never leak a contribution or a contribution total.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, scope_to_workspace
from app.models.goal import Goal, GoalContribution
from app.schemas.goal import GoalContributionCreate, GoalCreate, GoalRead, GoalUpdate

_SELECT_WITH_TOTAL = (
    select(
        Goal.id,
        Goal.name,
        Goal.target_amount,
        Goal.target_date,
        func.coalesce(func.sum(GoalContribution.amount), 0).label("current_amount"),
    )
    .outerjoin(GoalContribution, GoalContribution.goal_id == Goal.id)
    .group_by(Goal.id, Goal.name, Goal.target_amount, Goal.target_date, Goal.created_at)
    .order_by(Goal.created_at)
)


def _to_read(row: Row) -> GoalRead:
    current = row.current_amount
    target = row.target_amount
    percent = float(current / target * 100) if target else 0.0
    return GoalRead(
        id=row.id,
        name=row.name,
        target_amount=target,
        target_date=row.target_date,
        current_amount=current,
        remaining=target - current,
        percent=percent,
        is_reached=current >= target,
    )


async def _read_one(session: AsyncSession, goal_id: int, context: RequestWorkspace) -> GoalRead:
    statement = scope_to_workspace(_SELECT_WITH_TOTAL, Goal, context).where(Goal.id == goal_id)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _to_read(row)


async def list_goals(session: AsyncSession, context: RequestWorkspace) -> list[GoalRead]:
    statement = scope_to_workspace(_SELECT_WITH_TOTAL, Goal, context)
    rows = (await session.execute(statement)).all()
    return [_to_read(row) for row in rows]


async def create_goal(
    session: AsyncSession, payload: GoalCreate, context: RequestWorkspace
) -> GoalRead:
    context.require_mutation()
    goal = Goal(
        name=payload.name,
        target_amount=payload.target_amount,
        target_date=payload.target_date,
        workspace_id=context.workspace_id,
    )
    session.add(goal)
    await session.commit()
    return GoalRead(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        current_amount=Decimal("0"),
        remaining=goal.target_amount,
        percent=0.0,
        is_reached=False,
    )


async def _scoped_goal(session: AsyncSession, goal_id: int, context: RequestWorkspace) -> Goal:
    """Resolve a goal through the workspace scope, or 404 without revealing
    that a foreign goal exists."""
    statement = scope_to_workspace(select(Goal), Goal, context).where(Goal.id == goal_id)
    goal = (await session.execute(statement)).scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


async def update_goal(
    session: AsyncSession, goal_id: int, payload: GoalUpdate, context: RequestWorkspace
) -> GoalRead:
    context.require_mutation()
    goal = await _scoped_goal(session, goal_id, context)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    await session.commit()
    return await _read_one(session, goal_id, context)


async def delete_goal(session: AsyncSession, goal_id: int, context: RequestWorkspace) -> None:
    context.require_mutation()
    goal = await _scoped_goal(session, goal_id, context)
    await session.delete(goal)
    await session.commit()


async def add_contribution(
    session: AsyncSession, goal_id: int, payload: GoalContributionCreate, context: RequestWorkspace
) -> GoalRead:
    context.require_mutation()
    # Resolve the parent goal first: GoalContribution carries no workspace_id,
    # so its ownership is only ever the goal's, and a foreign goal id must 404
    # before any row is written.
    await _scoped_goal(session, goal_id, context)
    session.add(
        GoalContribution(goal_id=goal_id, amount=payload.amount, date=payload.date, note=payload.note)
    )
    await session.commit()
    return await _read_one(session, goal_id, context)