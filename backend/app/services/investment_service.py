from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.enums import (
    AccountType,
    AssetClass,
    CapitalRole,
    ExchangeRateSource,
    RiskLevel,
    SecurityTradeType,
    TransactionPurpose,
    TransactionType,
)
from app.models.investment import InvestmentPortfolio, Security, SecurityDividend, SecurityPrice, SecurityTrade
from app.models.transaction import Transaction
from app.schemas.investment import (
    InvestmentPortfolioCreate,
    InvestmentPortfolioRead,
    SecurityCreate,
    SecurityDividendCreate,
    SecurityDividendRead,
    SecurityPositionRead,
    SecurityPriceCreate,
    SecurityTradeCreate,
    SecurityTradeRead,
)
from app.services.exchange_rate_service import get_exchange_rate

_SECURITY_EAGER = (
    selectinload(Security.portfolio).selectinload(InvestmentPortfolio.account),
    selectinload(Security.trades),
    selectinload(Security.dividends),
    selectinload(Security.prices),
)


async def _security(session: AsyncSession, asset_id: int) -> Security:
    row = (
        await session.execute(select(Security).options(*_SECURITY_EAGER).where(Security.asset_id == asset_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Security not found")
    return row


async def _rate(session: AsyncSession, event_date, currency: str, manual: Decimal | None) -> Decimal:
    return manual or (await get_exchange_rate(session, event_date, currency)).rate_to_kzt


def _position_values(security: Security) -> tuple[Decimal, Decimal | None, Decimal, Decimal]:
    quantity = Decimal("0")
    average: Decimal | None = None
    realized = Decimal("0")
    for trade in sorted(security.trades, key=lambda item: (item.date, item.id)):
        if trade.type == SecurityTradeType.BUY:
            existing_cost = (average or Decimal("0")) * quantity
            added_cost = trade.quantity * trade.price_per_unit + trade.fee
            quantity += trade.quantity
            average = (existing_cost + added_cost) / quantity
        else:
            if trade.quantity > quantity:
                raise HTTPException(422, "Sell quantity exceeds the position available on that date")
            realized += trade.quantity * (trade.price_per_unit - (average or Decimal("0"))) - trade.fee
            quantity -= trade.quantity
            if quantity == 0:
                average = None
    cost_basis = (average or Decimal("0")) * quantity
    return quantity, average, cost_basis, realized


def _to_position(security: Security) -> SecurityPositionRead:
    quantity, average, cost_basis, realized = _position_values(security)
    latest = max(security.prices, key=lambda item: (item.as_of_date, item.id), default=None)
    current_price = latest.price_per_unit if latest else None
    current_value = quantity * current_price if current_price is not None else None
    unrealized = current_value - cost_basis if current_value is not None else None
    net_dividends = sum((item.gross_amount - item.tax_amount for item in security.dividends), Decimal("0"))
    total_return = realized + (unrealized or Decimal("0")) + net_dividends
    return SecurityPositionRead(
        asset_id=security.asset_id,
        portfolio_id=security.portfolio_id,
        name=security.name,
        ticker=security.ticker,
        isin=security.isin,
        exchange=security.exchange,
        currency=security.currency,
        quantity=quantity,
        average_cost=average,
        cost_basis=cost_basis,
        current_price=current_price,
        current_value=current_value,
        realized_profit=realized,
        unrealized_profit=unrealized,
        net_dividends=net_dividends,
        total_return=total_return,
        trades=[SecurityTradeRead.model_validate(row) for row in sorted(security.trades, key=lambda item: (item.date, item.id), reverse=True)],
        dividends=[SecurityDividendRead.model_validate(row) for row in sorted(security.dividends, key=lambda item: (item.date, item.id), reverse=True)],
    )


def _cash_transaction(
    account_id: int,
    tx_type: TransactionType,
    amount: Decimal,
    event_date,
    description: str,
    purpose: TransactionPurpose,
    rate: Decimal,
    currency: str,
) -> Transaction:
    rounded = amount.quantize(Decimal("0.01"))
    return Transaction(
        account_id=account_id,
        type=tx_type,
        amount=rounded,
        # Security currency == the portfolio cash account's (enforced in
        # create_security), so the cash leg is denominated in it and the two
        # amounts are the same figure.
        currency=currency,
        transaction_amount=rounded,
        exchange_rate_to_kzt=rate,
        base_amount_kzt=(rounded * rate).quantize(Decimal("0.01")),
        exchange_rate_source=ExchangeRateSource.MANUAL,
        purpose=purpose,
        description=description,
        date=event_date,
    )


def _update_cash_transaction(
    row: Transaction,
    tx_type: TransactionType,
    amount: Decimal,
    event_date,
    description: str,
    purpose: TransactionPurpose,
    rate: Decimal,
    currency: str,
) -> None:
    rounded = amount.quantize(Decimal("0.01"))
    row.type = tx_type
    row.amount = rounded
    # Keep the transaction's own figure in step with the account-side debit —
    # they're the same number for a same-currency row.
    row.currency = currency
    row.transaction_amount = rounded
    row.exchange_rate_to_kzt = rate
    row.base_amount_kzt = (rounded * rate).quantize(Decimal("0.01"))
    row.exchange_rate_source = ExchangeRateSource.MANUAL
    row.purpose = purpose
    row.description = description
    row.date = event_date


async def list_portfolios(session: AsyncSession) -> list[InvestmentPortfolioRead]:
    rows = (await session.execute(select(InvestmentPortfolio).order_by(InvestmentPortfolio.id))).scalars().all()
    return [InvestmentPortfolioRead.model_validate(row) for row in rows]


async def create_portfolio(session: AsyncSession, payload: InvestmentPortfolioCreate) -> InvestmentPortfolioRead:
    account = await session.get(Account, payload.account_id)
    if account is None or account.type != AccountType.INVESTMENT:
        raise HTTPException(400, "Portfolio account must be an investment account")
    row = InvestmentPortfolio(**payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return InvestmentPortfolioRead.model_validate(row)


async def create_security(session: AsyncSession, payload: SecurityCreate) -> SecurityPositionRead:
    portfolio = await session.get(InvestmentPortfolio, payload.portfolio_id, options=[selectinload(InvestmentPortfolio.account)])
    if portfolio is None:
        raise HTTPException(404, "Investment portfolio not found")
    currency = payload.currency.upper()
    if portfolio.account.currency.upper() != currency:
        raise HTTPException(422, "Security currency must match the portfolio cash account currency")
    asset = Asset(
        name=payload.name,
        asset_class=AssetClass.INVESTMENTS,
        currency=currency,
        capital_role=CapitalRole.INCOME,
        risk_level=RiskLevel.MEDIUM,
    )
    session.add(asset)
    await session.flush()
    session.add(
        Security(
            asset_id=asset.id,
            portfolio_id=payload.portfolio_id,
            name=payload.name,
            ticker=payload.ticker.upper(),
            isin=payload.isin.upper() if payload.isin else None,
            exchange=payload.exchange,
            currency=currency,
        )
    )
    await session.commit()
    return _to_position(await _security(session, asset.id))


async def list_positions(session: AsyncSession, portfolio_id: int | None = None) -> list[SecurityPositionRead]:
    stmt = select(Security).options(*_SECURITY_EAGER).order_by(Security.ticker)
    if portfolio_id is not None:
        stmt = stmt.where(Security.portfolio_id == portfolio_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_position(row) for row in rows]


async def create_trade(session: AsyncSession, asset_id: int, payload: SecurityTradeCreate) -> SecurityPositionRead:
    security = await _security(session, asset_id)
    if payload.external_id:
        duplicate = await session.scalar(
            select(SecurityTrade.id).where(SecurityTrade.asset_id == asset_id, SecurityTrade.external_id == payload.external_id)
        )
        if duplicate:
            raise HTTPException(409, "Trade external_id already imported")
    if payload.type == SecurityTradeType.SELL:
        quantity, _, _, _ = _position_values(security)
        if payload.quantity > quantity:
            raise HTTPException(422, "Sell quantity exceeds current position")
    rate = await _rate(session, payload.date, security.currency, payload.exchange_rate_to_kzt)
    principal = payload.quantity * payload.price_per_unit
    cash = _cash_transaction(
        security.portfolio.account_id,
        TransactionType.EXPENSE if payload.type == SecurityTradeType.BUY else TransactionType.INCOME,
        principal,
        payload.date,
        f"{payload.type.value.upper()} {security.ticker}",
        TransactionPurpose.INVESTMENT_TRADE,
        rate,
        security.currency,
    )
    session.add(cash)
    await session.flush()
    fee_tx = None
    if payload.fee:
        fee_tx = _cash_transaction(
            security.portfolio.account_id,
            TransactionType.EXPENSE,
            payload.fee,
            payload.date,
            f"Fee: {security.ticker}",
            TransactionPurpose.FEE,
            rate,
            security.currency,
        )
        session.add(fee_tx)
        await session.flush()
    session.add(
        SecurityTrade(
            asset_id=asset_id,
            type=payload.type,
            quantity=payload.quantity,
            price_per_unit=payload.price_per_unit,
            fee=payload.fee,
            date=payload.date,
            exchange_rate_to_kzt=rate,
            cash_transaction_id=cash.id,
            fee_transaction_id=fee_tx.id if fee_tx else None,
            external_id=payload.external_id,
        )
    )
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def create_dividend(session: AsyncSession, asset_id: int, payload: SecurityDividendCreate) -> SecurityPositionRead:
    security = await _security(session, asset_id)
    if payload.external_id:
        duplicate = await session.scalar(
            select(SecurityDividend.id).where(
                SecurityDividend.asset_id == asset_id, SecurityDividend.external_id == payload.external_id
            )
        )
        if duplicate:
            raise HTTPException(409, "Dividend external_id already imported")
    rate = await _rate(session, payload.date, security.currency, payload.exchange_rate_to_kzt)
    income = _cash_transaction(
        security.portfolio.account_id,
        TransactionType.INCOME,
        payload.gross_amount,
        payload.date,
        f"Dividend: {security.ticker}",
        TransactionPurpose.DIVIDEND,
        rate,
        security.currency,
    )
    session.add(income)
    await session.flush()
    tax_tx = None
    if payload.tax_amount:
        tax_tx = _cash_transaction(
            security.portfolio.account_id,
            TransactionType.EXPENSE,
            payload.tax_amount,
            payload.date,
            f"Dividend tax: {security.ticker}",
            TransactionPurpose.TAX,
            rate,
            security.currency,
        )
        session.add(tax_tx)
        await session.flush()
    session.add(
        SecurityDividend(
            asset_id=asset_id,
            gross_amount=payload.gross_amount,
            tax_amount=payload.tax_amount,
            date=payload.date,
            exchange_rate_to_kzt=rate,
            income_transaction_id=income.id,
            tax_transaction_id=tax_tx.id if tax_tx else None,
            external_id=payload.external_id,
        )
    )
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def set_price(session: AsyncSession, asset_id: int, payload: SecurityPriceCreate) -> SecurityPositionRead:
    security = await _security(session, asset_id)
    rate = await _rate(session, payload.as_of_date, security.currency, payload.exchange_rate_to_kzt)
    await session.execute(
        pg_insert(SecurityPrice)
        .values(
            asset_id=asset_id,
            price_per_unit=payload.price_per_unit,
            as_of_date=payload.as_of_date,
            exchange_rate_to_kzt=rate,
        )
        .on_conflict_do_update(
            index_elements=[SecurityPrice.asset_id, SecurityPrice.as_of_date],
            set_={"price_per_unit": payload.price_per_unit, "exchange_rate_to_kzt": rate},
        )
    )
    await session.flush()
    session.expire(security, ["prices"])
    security = await _security(session, asset_id)
    quantity, _, _, _ = _position_values(security)
    value = (quantity * payload.price_per_unit).quantize(Decimal("0.01"))
    await session.execute(
        pg_insert(AssetValuation)
        .values(
            asset_id=asset_id,
            value=value,
            as_of_date=payload.as_of_date,
            exchange_rate_to_kzt=rate,
            base_value_kzt=(value * rate).quantize(Decimal("0.01")),
        )
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={"value": value, "exchange_rate_to_kzt": rate, "base_value_kzt": (value * rate).quantize(Decimal("0.01"))},
        )
    )
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def delete_trade(session: AsyncSession, trade_id: int) -> SecurityPositionRead:
    trade = await session.get(SecurityTrade, trade_id)
    if trade is None:
        raise HTTPException(404, "Trade not found")
    asset_id = trade.asset_id
    cash_id, fee_id = trade.cash_transaction_id, trade.fee_transaction_id
    await session.delete(trade)
    await session.flush()
    session.expire_all()
    # Replay before committing: removing an earlier buy may make a later sell invalid.
    _position_values(await _security(session, asset_id))
    for transaction_id in (fee_id, cash_id):
        if transaction_id is not None:
            row = await session.get(Transaction, transaction_id)
            if row is not None:
                await session.delete(row)
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def update_trade(session: AsyncSession, trade_id: int, payload: SecurityTradeCreate) -> SecurityPositionRead:
    trade = await session.get(SecurityTrade, trade_id)
    if trade is None:
        raise HTTPException(404, "Trade not found")
    asset_id = trade.asset_id
    security = await _security(session, asset_id)
    if payload.external_id:
        duplicate = await session.scalar(
            select(SecurityTrade.id).where(
                SecurityTrade.asset_id == asset_id,
                SecurityTrade.external_id == payload.external_id,
                SecurityTrade.id != trade.id,
            )
        )
        if duplicate:
            raise HTTPException(409, "Trade external_id already imported")
    rate = await _rate(session, payload.date, security.currency, payload.exchange_rate_to_kzt)
    trade.type = payload.type
    trade.quantity = payload.quantity
    trade.price_per_unit = payload.price_per_unit
    trade.fee = payload.fee
    trade.date = payload.date
    trade.exchange_rate_to_kzt = rate
    trade.external_id = payload.external_id
    cash = await session.get(Transaction, trade.cash_transaction_id)
    _update_cash_transaction(
        cash,
        TransactionType.EXPENSE if payload.type == SecurityTradeType.BUY else TransactionType.INCOME,
        payload.quantity * payload.price_per_unit,
        payload.date,
        f"{payload.type.value.upper()} {security.ticker}",
        TransactionPurpose.INVESTMENT_TRADE,
        rate,
        security.currency,
    )
    fee_tx = await session.get(Transaction, trade.fee_transaction_id) if trade.fee_transaction_id else None
    if payload.fee:
        if fee_tx is None:
            fee_tx = _cash_transaction(security.portfolio.account_id, TransactionType.EXPENSE, payload.fee, payload.date, f"Fee: {security.ticker}", TransactionPurpose.FEE, rate, security.currency)
            session.add(fee_tx)
            await session.flush()
            trade.fee_transaction_id = fee_tx.id
        else:
            _update_cash_transaction(fee_tx, TransactionType.EXPENSE, payload.fee, payload.date, f"Fee: {security.ticker}", TransactionPurpose.FEE, rate, security.currency)
    elif fee_tx is not None:
        trade.fee_transaction_id = None
        await session.flush()
        await session.delete(fee_tx)
    await session.flush()
    session.expire_all()
    _position_values(await _security(session, asset_id))
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def delete_dividend(session: AsyncSession, dividend_id: int) -> SecurityPositionRead:
    dividend = await session.get(SecurityDividend, dividend_id)
    if dividend is None:
        raise HTTPException(404, "Dividend not found")
    asset_id = dividend.asset_id
    transaction_ids = (dividend.tax_transaction_id, dividend.income_transaction_id)
    await session.delete(dividend)
    await session.flush()
    for transaction_id in transaction_ids:
        if transaction_id is not None:
            row = await session.get(Transaction, transaction_id)
            if row is not None:
                await session.delete(row)
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))


async def update_dividend(session: AsyncSession, dividend_id: int, payload: SecurityDividendCreate) -> SecurityPositionRead:
    dividend = await session.get(SecurityDividend, dividend_id)
    if dividend is None:
        raise HTTPException(404, "Dividend not found")
    asset_id = dividend.asset_id
    security = await _security(session, asset_id)
    rate = await _rate(session, payload.date, security.currency, payload.exchange_rate_to_kzt)
    dividend.gross_amount = payload.gross_amount
    dividend.tax_amount = payload.tax_amount
    dividend.date = payload.date
    dividend.exchange_rate_to_kzt = rate
    dividend.external_id = payload.external_id
    income = await session.get(Transaction, dividend.income_transaction_id)
    _update_cash_transaction(income, TransactionType.INCOME, payload.gross_amount, payload.date, f"Dividend: {security.ticker}", TransactionPurpose.DIVIDEND, rate, security.currency)
    tax_tx = await session.get(Transaction, dividend.tax_transaction_id) if dividend.tax_transaction_id else None
    if payload.tax_amount:
        if tax_tx is None:
            tax_tx = _cash_transaction(security.portfolio.account_id, TransactionType.EXPENSE, payload.tax_amount, payload.date, f"Dividend tax: {security.ticker}", TransactionPurpose.TAX, rate, security.currency)
            session.add(tax_tx)
            await session.flush()
            dividend.tax_transaction_id = tax_tx.id
        else:
            _update_cash_transaction(tax_tx, TransactionType.EXPENSE, payload.tax_amount, payload.date, f"Dividend tax: {security.ticker}", TransactionPurpose.TAX, rate, security.currency)
    elif tax_tx is not None:
        dividend.tax_transaction_id = None
        await session.flush()
        await session.delete(tax_tx)
    await session.commit()
    session.expire_all()
    return _to_position(await _security(session, asset_id))
