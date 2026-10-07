from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.schemas.recurring import RecurringTransactionCreate, RecurringTransactionRead, RecurringTransactionUpdate
from app.services.recurring_service import (
    create_recurring,
    delete_recurring,
    list_recurring,
    post_recurring,
    update_recurring,
)

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("", response_model=list[RecurringTransactionRead])
async def read_recurring(
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> list[RecurringTransactionRead]:
    return await list_recurring(session, context)


@router.post("", response_model=RecurringTransactionRead, status_code=201)
async def create_recurring_route(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> RecurringTransactionRead:
    return await create_recurring(session, payload, context)


@router.patch("/{recurring_id}", response_model=RecurringTransactionRead)
async def update_recurring_route(
    recurring_id: int,
    payload: RecurringTransactionUpdate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> RecurringTransactionRead:
    return await update_recurring(session, recurring_id, payload, context)


@router.delete("/{recurring_id}", status_code=204)
async def delete_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> None:
    await delete_recurring(session, recurring_id, context)


@router.post("/{recurring_id}/post", response_model=RecurringTransactionRead, status_code=201)
async def post_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> RecurringTransactionRead:
    return await post_recurring(session, recurring_id, context)