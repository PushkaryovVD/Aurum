"""Account CRUD, plus each account's live balance — summed from its
Transaction rows (income adds, expense subtracts, a transfer moves the
amount from the source account to the destination account) rather than
stored, the same "derive it, don't duplicate it" approach
net_worth_service.py uses for Cash.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance


async def account_balances(session: AsyncSession) -> tuple[dict[int, Decimal], dict[int, int]]:
    """Every account's live balance and how many transactions it holds, in one
    pass. The balance feeds the Accounts page and the Dashboard's totals; the
    count is what tells the UI whether an account's currency can still be
    changed (see update_account).
    """
    result = await session.execute(
        select(
            Transaction.type,
            Transaction.amount,
            Transaction.transfer_amount,
            Transaction.account_id,
            Transaction.transfer_account_id,
        )
    )
    balances: dict[int, Decimal] = defaultdict(Decimal)
    counts: dict[int, int] = defaultdict(int)
    for tx_type, amount, transfer_amount, account_id, transfer_account_id in result.all():
        # A transfer row belongs to its source account — that's the side whose
        # currency the row is denominated in.
        counts[account_id] += 1
        if tx_type == TransactionType.INCOME:
            balances[account_id] += amount
        elif tx_type == TransactionType.EXPENSE:
            balances[account_id] -= amount
        elif tx_type == TransactionType.TRANSFER:
            balances[account_id] -= amount
            if transfer_account_id is not None:
                balances[transfer_account_id] += transfer_amount if transfer_amount is not None else amount
    return balances, counts


def _to_read(account: Account, balance: Decimal, transaction_count: int) -> AccountWithBalance:
    return AccountWithBalance(
        id=account.id,
        name=account.name,
        type=account.type,
        currency=account.currency,
        color=account.color,
        is_archived=account.is_archived,
        balance=balance,
        transaction_count=transaction_count,
    )


async def list_accounts(session: AsyncSession, include_archived: bool) -> list[AccountWithBalance]:
    stmt = select(Account).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = (await session.execute(stmt)).scalars().all()
    balances, counts = await account_balances(session)
    return [
        _to_read(account, balances.get(account.id, Decimal("0")), counts.get(account.id, 0))
        for account in accounts
    ]


async def create_account(session: AsyncSession, payload: AccountCreate) -> AccountWithBalance:
    account = Account(**payload.model_dump())
    session.add(account)
    await session.commit()
    await session.refresh(account)
    # A brand-new account has no transactions yet — no need to query.
    return _to_read(account, Decimal("0"), 0)


async def update_account(session: AsyncSession, account_id: int, payload: AccountUpdate) -> AccountWithBalance:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    updates = payload.model_dump(exclude_unset=True)

    new_currency = updates.get("currency")
    if new_currency is not None and new_currency.upper() != account.currency.upper():
        # Every existing transaction on this account is recorded in the old
        # currency: its amount, its KZT snapshot and its own transaction
        # currency were all derived from it. Re-labelling the account would
        # silently reinterpret that history (a 100 KZT balance becoming 100
        # USD), so the change is refused outright rather than converted — a
        # clear error beats a wrong number.
        _, counts = await account_balances(session)
        if counts.get(account_id, 0) > 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Account currency cannot be changed while the account has transactions — "
                    "its history is recorded in the current currency. Create a separate account instead."
                ),
            )

    for field, value in updates.items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances, counts = await account_balances(session)
    return _to_read(account, balances.get(account.id, Decimal("0")), counts.get(account.id, 0))


async def delete_account(session: AsyncSession, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    await session.commit()
