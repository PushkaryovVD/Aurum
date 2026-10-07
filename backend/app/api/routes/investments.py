from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.schemas.investment import (
    InvestmentPortfolioCreate,
    InvestmentPortfolioRead,
    SecurityCreate,
    SecurityDividendCreate,
    SecurityPositionRead,
    SecurityPriceCreate,
    SecurityTradeCreate,
)
from app.services import investment_service

router = APIRouter(prefix="/investments", tags=["investments"])


@router.get("/portfolios", response_model=list[InvestmentPortfolioRead])
async def portfolios(
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.list_portfolios(session, context)


@router.post("/portfolios", response_model=InvestmentPortfolioRead, status_code=201)
async def add_portfolio(
    payload: InvestmentPortfolioCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.create_portfolio(session, payload, context)


@router.get("/positions", response_model=list[SecurityPositionRead])
async def positions(
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.list_positions(session, portfolio_id, context)


@router.post("/securities", response_model=SecurityPositionRead, status_code=201)
async def add_security(
    payload: SecurityCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.create_security(session, payload, context)


@router.post("/securities/{asset_id}/trades", response_model=SecurityPositionRead, status_code=201)
async def add_trade(
    asset_id: int,
    payload: SecurityTradeCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.create_trade(session, asset_id, payload, context)


@router.delete("/trades/{trade_id}", response_model=SecurityPositionRead)
async def remove_trade(
    trade_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.delete_trade(session, trade_id, context)


@router.patch("/trades/{trade_id}", response_model=SecurityPositionRead)
async def edit_trade(
    trade_id: int,
    payload: SecurityTradeCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.update_trade(session, trade_id, payload, context)


@router.post("/securities/{asset_id}/dividends", response_model=SecurityPositionRead, status_code=201)
async def add_dividend(
    asset_id: int,
    payload: SecurityDividendCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.create_dividend(session, asset_id, payload, context)


@router.delete("/dividends/{dividend_id}", response_model=SecurityPositionRead)
async def remove_dividend(
    dividend_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.delete_dividend(session, dividend_id, context)


@router.patch("/dividends/{dividend_id}", response_model=SecurityPositionRead)
async def edit_dividend(
    dividend_id: int,
    payload: SecurityDividendCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.update_dividend(session, dividend_id, payload, context)


@router.put("/securities/{asset_id}/price", response_model=SecurityPositionRead)
async def update_price(
    asset_id: int,
    payload: SecurityPriceCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await investment_service.set_price(session, asset_id, payload, context)