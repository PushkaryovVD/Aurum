from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.schemas.advice import AdviceResponse
from app.services.advice_service import get_advice

router = APIRouter(prefix="/advice", tags=["advice"])


@router.get("", response_model=AdviceResponse)
async def read_advice(
    session: AsyncSession = Depends(get_session), context: RequestWorkspace = Depends(get_request_workspace)
) -> AdviceResponse:
    return await get_advice(session, context)
