"""Recurring transaction templates: CRUD, plus "post now" — a one-click
action that creates a real Transaction from the template. Deliberately not a
background job (see also insights_service.py's docstring on scope): the
schedule only advances when the user actually clicks Post, so a missed
week never silently back-fills a pile of transactions.

Every read and write is authorized against the request's workspace (see
app/api/deps.py). A NULL workspace is the legacy auth-disabled namespace and
keeps its original installation-wide behavior; an authenticated caller only
ever sees and mutates its own workspace's templates.
"""
import calendar
from datetime import date as date_
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import RequestWorkspace, scope_to_workspace
from app.models.account import Account
from app.models.category import Category
from app.models.enums import CategoryKind, RecurringFrequency, TransactionType
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.schemas.recurring import RecurringTransactionCreate, RecurringTransactionRead, RecurringTransactionUpdate

_EAGER = (
    selectinload(RecurringTransaction.account),
    selectinload(RecurringTransaction.category),
    selectinload(RecurringTransaction.transfer_account),
)

_TYPE_TO_CATEGORY_KIND = {
    TransactionType.INCOME: CategoryKind.INCOME,
    TransactionType.EXPENSE: CategoryKind.EXPENSE,
}


async def _ensure_category_matches_type(
    session: AsyncSession,
    category_id: int | None,
    transaction_type: TransactionType,
    context: RequestWorkspace,
) -> None:
    if category_id is None:
        return
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    statement = scope_to_workspace(select(Category).where(Category.id == category_id), Category, context)
    category = (await session.execute(statement)).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} recurring transaction",
        )


async def _resolve_account(session: AsyncSession, account_id: int, context: RequestWorkspace) -> Account:
    """Fetch an account through the workspace scope so a foreign id reads as
    absent — the same non-disclosure rule the get-by-id path follows."""
    statement = scope_to_workspace(select(Account).where(Account.id == account_id), Account, context)
    account = (await session.execute(statement)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=400, detail="Account not found")
    return account


async def _ensure_references_in_scope(
    session: AsyncSession,
    account_id: int,
    transfer_account_id: int | None,
    context: RequestWorkspace,
) -> None:
    await _resolve_account(session, account_id, context)
    if transfer_account_id is not None:
        await _resolve_account(session, transfer_account_id, context)


def _advance(day: date_, frequency: RecurringFrequency) -> date_:
    if frequency == RecurringFrequency.WEEKLY:
        return day + timedelta(days=7)
    if frequency == RecurringFrequency.MONTHLY:
        year = day.year + (day.month // 12)
        month = day.month % 12 + 1
        clamped_day = min(day.day, calendar.monthrange(year, month)[1])
        return date_(year, month, clamped_day)
    # YEARLY — Feb 29 anchors fall back to Feb 28 in non-leap years.
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def _next_due_date(recurring: RecurringTransaction) -> date_:
    if recurring.last_posted_date is None:
        return recurring.anchor_date
    return _advance(recurring.last_posted_date, recurring.frequency)


def _to_read(recurring: RecurringTransaction) -> RecurringTransactionRead:
    next_due = _next_due_date(recurring)
    today = date_.today()
    return RecurringTransactionRead(
        id=recurring.id,
        account_id=recurring.account_id,
        account_name=recurring.account.name,
        category_id=recurring.category_id,
        category_name=recurring.category.name if recurring.category else None,
        category_color=recurring.category.color if recurring.category else None,
        category_icon=recurring.category.icon if recurring.category else None,
        transfer_account_id=recurring.transfer_account_id,
        transfer_account_name=recurring.transfer_account.name if recurring.transfer_account else None,
        type=recurring.type,
        amount=recurring.amount,
        description=recurring.description,
        merchant=recurring.merchant,
        notes=recurring.notes,
        frequency=recurring.frequency,
        anchor_date=recurring.anchor_date,
        last_posted_date=recurring.last_posted_date,
        is_active=recurring.is_active,
        next_due_date=next_due,
        is_due=recurring.is_active and next_due <= today,
        days_until_due=(next_due - today).days,
    )


async def _get_or_404(
    session: AsyncSession, recurring_id: int, context: RequestWorkspace
) -> RecurringTransaction:
    statement = scope_to_workspace(
        select(RecurringTransaction).options(*_EAGER).where(RecurringTransaction.id == recurring_id),
        RecurringTransaction,
        context,
    )
    recurring = (await session.execute(statement)).scalar_one_or_none()
    if recurring is None:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    return recurring


async def list_recurring(session: AsyncSession, context: RequestWorkspace) -> list[RecurringTransactionRead]:
    statement = scope_to_workspace(
        select(RecurringTransaction).options(*_EAGER), RecurringTransaction, context
    ).order_by(RecurringTransaction.id)
    result = await session.execute(statement)
    return [_to_read(row) for row in result.scalars().all()]


async def create_recurring(
    session: AsyncSession, payload: RecurringTransactionCreate, context: RequestWorkspace
) -> RecurringTransactionRead:
    context.require_mutation()
    await _ensure_category_matches_type(session, payload.category_id, payload.type, context)
    await _ensure_references_in_scope(
        session, payload.account_id, payload.transfer_account_id, context
    )
    recurring = RecurringTransaction(**payload.model_dump(), workspace_id=context.workspace_id)
    session.add(recurring)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring.id, context))


async def update_recurring(
    session: AsyncSession, recurring_id: int, payload: RecurringTransactionUpdate, context: RequestWorkspace
) -> RecurringTransactionRead:
    context.require_mutation()
    recurring = await _get_or_404(session, recurring_id, context)
    updates = payload.model_dump(exclude_unset=True)
    effective_type = updates.get("type", recurring.type)
    effective_category_id = updates.get("category_id", recurring.category_id)
    await _ensure_category_matches_type(session, effective_category_id, effective_type, context)
    account_id = updates.get("account_id", recurring.account_id)
    transfer_account_id = updates.get("transfer_account_id", recurring.transfer_account_id)
    await _ensure_references_in_scope(session, account_id, transfer_account_id, context)
    for field, value in updates.items():
        setattr(recurring, field, value)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id, context))


async def delete_recurring(session: AsyncSession, recurring_id: int, context: RequestWorkspace) -> None:
    context.require_mutation()
    recurring = await _get_or_404(session, recurring_id, context)
    await session.delete(recurring)
    await session.commit()


async def post_recurring(
    session: AsyncSession, recurring_id: int, context: RequestWorkspace
) -> RecurringTransactionRead:
    """Creates a real Transaction from the template, dated today, and moves
    last_posted_date forward — the only thing that advances the schedule.

    Both rows inherit the request workspace: the new Transaction is inserted
    with workspace_id=context.workspace_id and its account is resolved through
    the workspace scope, so a template can never mint a transaction that
    reaches outside the caller's own data.
    """
    context.require_mutation()
    recurring = await _get_or_404(session, recurring_id, context)
    account = await _resolve_account(session, recurring.account_id, context)
    today = date_.today()

    session.add(
        Transaction(
            workspace_id=context.workspace_id,
            account_id=recurring.account_id,
            category_id=recurring.category_id,
            transfer_account_id=recurring.transfer_account_id,
            type=recurring.type,
            amount=recurring.amount,
            # The template carries no currency of its own, so a posted row is
            # denominated in its account's — with both amounts the same figure.
            currency=account.currency.upper(),
            transaction_amount=recurring.amount,
            description=recurring.description,
            merchant=recurring.merchant,
            notes=recurring.notes,
            date=today,
        )
    )
    recurring.last_posted_date = today
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id, context))