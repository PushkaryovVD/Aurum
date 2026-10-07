from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.schemas.goal import GoalContributionCreate, GoalCreate, GoalRead, GoalUpdate
from app.services.goal_service import add_contribution, create_goal, delete_goal, list_goals, update_goal

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalRead])
async def read_goals(
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> list[GoalRead]:
    return await list_goals(session, context)


@router.post("", response_model=GoalRead, status_code=201)
async def create_goal_route(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> GoalRead:
    return await create_goal(session, payload, context)


@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal_route(
    goal_id: int,
    payload: GoalUpdate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> GoalRead:
    return await update_goal(session, goal_id, payload, context)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal_route(
    goal_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> None:
    await delete_goal(session, goal_id, context)


@router.post("/{goal_id}/contributions", response_model=GoalRead, status_code=201)
async def add_contribution_route(
    goal_id: int,
    payload: GoalContributionCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> GoalRead:
    return await add_contribution(session, goal_id, payload, context)