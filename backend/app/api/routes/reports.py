from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.models.enums import CategoryKind
from app.schemas.reports import CategoryRankingReport, CategorySpendingReport
from app.services.reports_service import get_category_ranking_report, get_category_spending_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/category-spending", response_model=CategorySpendingReport)
async def read_category_spending_report(
    category_id: int,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> CategorySpendingReport:
    return await get_category_spending_report(session, category_id, start_date, end_date, context)


@router.get("/category-ranking", response_model=CategoryRankingReport)
async def read_category_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> CategoryRankingReport:
    return await get_category_ranking_report(session, kind, start_date, end_date, context)
