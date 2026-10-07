"""Envelope calculations over the ledger without mutating ledger/account rows."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, scope_to_workspace
from app.models.account import Account
from app.models.category import Category
from app.models.envelope import EnvelopeAllocation, EnvelopeAuditLog, EnvelopeMonth, EnvelopeTemplate, EnvelopeTemplateItem
from app.models.enums import CategoryKind, TransactionType
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.envelope import (
    EnvelopeAllocationInput,
    EnvelopeFundInput,
    EnvelopeFundResult,
    EnvelopeItem,
    EnvelopeMonthSummary,
    EnvelopeMoveInput,
    EnvelopeShortfall,
    EnvelopeStatus,
    EnvelopeWarning,
    MonthRef,
)
from app.services.currency import split_amount_kzt, transaction_amount_kzt

ZERO = Decimal("0.00")
MonthKey = tuple[int, int]


def _month_key(value: date) -> MonthKey:
    return value.year, value.month


def _next_month(key: MonthKey) -> MonthKey:
    return (key[0] + 1, 1) if key[1] == 12 else (key[0], key[1] + 1)


def _months(start: MonthKey, end: MonthKey):
    current = start
    while current <= end:
        yield current
        current = _next_month(current)


async def _expense_category(session: AsyncSession, category_id: int, context: RequestWorkspace | None = None) -> Category:
    stmt = select(Category).where(Category.id == category_id)
    if context is not None:
        stmt = scope_to_workspace(stmt, Category, context)
    category = (await session.execute(stmt)).scalar_one_or_none()
    if category is None or category.kind != CategoryKind.EXPENSE:
        raise HTTPException(400, "Envelopes require an expense category")
    return category


async def _month_row(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeMonth | None:
    stmt = select(EnvelopeMonth).where(EnvelopeMonth.year == year, EnvelopeMonth.month == month)
    if context is not None:
        stmt = scope_to_workspace(stmt, EnvelopeMonth, context)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _require_open_month(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeMonth:
    row = await _month_row(session, year, month, context)
    if row is None:
        raise HTTPException(404, "Envelope month is not open")
    if row.is_closed:
        raise HTTPException(409, f"Envelope month {year}-{month:02d} is closed")
    return row


async def _scoped(session: AsyncSession, statement, model, context: RequestWorkspace | None):
    """Apply the request workspace filter when the caller is authenticated.

    ``None``/``workspace_id is None`` keeps the legacy auth-disabled behavior:
    every row (including the NULL-workspace namespace) remains visible.
    """
    if context is not None:
        statement = scope_to_workspace(statement, model, context)
    return statement


async def open_month(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    row = await _month_row(session, year, month, context)
    if row is None:
        session.add(EnvelopeMonth(year=year, month=month, workspace_id=None if context is None else context.workspace_id))
        await session.commit()
    return await get_status(session, year, month, context)


async def list_months(session: AsyncSession, context: RequestWorkspace | None = None) -> list[EnvelopeMonthSummary]:
    stmt = select(EnvelopeMonth).order_by(EnvelopeMonth.year.desc(), EnvelopeMonth.month.desc())
    stmt = await _scoped(session, stmt, EnvelopeMonth, context)
    rows = list((await session.execute(stmt)).scalars())
    result = []
    for row in rows:
        status = await get_status(session, row.year, row.month, context)
        result.append(
            EnvelopeMonthSummary(
                year=row.year, month=row.month, is_closed=row.is_closed, has_ledger_drift=status.has_ledger_drift
            )
        )
    return result


async def list_audit(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> list[EnvelopeAuditLog]:
    """Audit history for a month, resolved through the workspace-scoped month.

    Audit rows carry no workspace column, so a workspace the month does not
    belong to yields nothing rather than another workspace's history.
    """
    if context is not None and await _month_row(session, year, month, context) is None:
        return []
    stmt = (
        select(EnvelopeAuditLog)
        .where(EnvelopeAuditLog.year == year, EnvelopeAuditLog.month == month)
        .order_by(EnvelopeAuditLog.id)
    )
    return list((await session.execute(stmt)).scalars())


async def _calculation_data(session: AsyncSession, target: MonthKey, context: RequestWorkspace | None = None):
    target_end = date(target[0], target[1], calendar.monthrange(*target)[1])
    month_stmt = select(EnvelopeMonth).order_by(EnvelopeMonth.year, EnvelopeMonth.month)
    month_stmt = await _scoped(session, month_stmt, EnvelopeMonth, context)
    month_rows = list((await session.execute(month_stmt)).scalars())
    categories = list((await session.execute(select(Category))).scalars())
    allocation_stmt = (
        select(EnvelopeAllocation)
        .where(or_(EnvelopeAllocation.year < target[0], (EnvelopeAllocation.year == target[0]) & (EnvelopeAllocation.month <= target[1])))
        .order_by(EnvelopeAllocation.year, EnvelopeAllocation.month, EnvelopeAllocation.category_id)
    )
    allocation_stmt = await _scoped(session, allocation_stmt, EnvelopeAllocation, context)
    allocations = list((await session.execute(allocation_stmt)).scalars())
    plain_stmt = (
        select(
            Transaction.date,
            Transaction.type,
            Transaction.category_id,
            Category.kind,
            Category.parent_id,
            Transaction.created_at,
            transaction_amount_kzt().label("amount_kzt"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(Transaction.date <= target_end)
    )
    plain_stmt = await _scoped(session, plain_stmt, Transaction, context)
    plain_stmt = await _scoped(session, plain_stmt, Account, context)
    plain_rows = (await session.execute(plain_stmt)).all()
    split_stmt = (
        select(
            Transaction.date,
            Transaction.type,
            TransactionSplit.category_id,
            Category.parent_id,
            split_amount_kzt().label("amount_kzt"),
        )
        .select_from(TransactionSplit)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == TransactionSplit.category_id)
        .where(Transaction.date <= target_end)
    )
    split_stmt = await _scoped(session, split_stmt, TransactionSplit, context)
    split_stmt = await _scoped(session, split_stmt, Transaction, context)
    split_stmt = await _scoped(session, split_stmt, Account, context)
    split_rows = (await session.execute(split_stmt)).all()
    return month_rows, categories, allocations, plain_rows, split_rows


async def get_status(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeStatus:
    target = (year, month)
    month_rows, categories, allocations, plain_rows, split_rows = await _calculation_data(session, target, context)
    row_by_month = {(row.year, row.month): row for row in month_rows}
    tracking_start = min(row_by_month, default=None)
    target_row = row_by_month.get(target)
    if tracking_start is None or target < tracking_start:
        return EnvelopeStatus(
            year=year,
            month=month,
            tracking_start=None if tracking_start is None else MonthRef(year=tracking_start[0], month=tracking_start[1]),
            is_closed=bool(target_row and target_row.is_closed),
            has_ledger_drift=False,
            fx_incomplete=False,
            income=ZERO,
            assigned=ZERO,
            available_to_assign=ZERO,
            items=[],
            warnings=[],
        )

    category_by_id = {category.id: category for category in categories}
    allocations_by_month: dict[MonthKey, dict[int, EnvelopeAllocation]] = defaultdict(dict)
    for allocation in allocations:
        key = (allocation.year, allocation.month)
        if key >= tracking_start:
            allocations_by_month[key][allocation.category_id] = allocation

    plain_by_month: dict[MonthKey, list] = defaultdict(list)
    split_by_month: dict[MonthKey, list] = defaultdict(list)
    income_before = ZERO
    earliest_income_before: date | None = None
    for tx in plain_rows:
        key = _month_key(tx.date)
        if key < tracking_start and tx.type == TransactionType.INCOME and tx.kind in {None, CategoryKind.INCOME} and tx.amount_kzt is not None:
            income_before += tx.amount_kzt
            earliest_income_before = min(earliest_income_before or tx.date, tx.date)
        if tracking_start <= key <= target:
            plain_by_month[key].append(tx)
    for split in split_rows:
        key = _month_key(split.date)
        if tracking_start <= key <= target:
            split_by_month[key].append(split)

    carry: dict[int, Decimal] = defaultdict(lambda: ZERO)
    policy: dict[int, tuple[bool, bool]] = defaultdict(lambda: (True, True))
    cumulative_unassigned = ZERO
    target_values: dict[int, dict] = {}
    target_income = ZERO
    target_assigned = ZERO
    target_fx_incomplete = False
    target_stray_refunds: dict[int, Decimal] = defaultdict(lambda: ZERO)

    for key in _months(tracking_start, target):
        current_rows = allocations_by_month.get(key, {})
        assigned = sum((row.assigned_amount for row in current_rows.values()), ZERO)
        income = ZERO
        stray_refunds = ZERO
        activity: dict[int, Decimal] = defaultdict(lambda: ZERO)
        fx_incomplete = False

        def resolve_envelope(category_id: int | None, parent_id: int | None) -> int | None:
            if category_id is not None and category_id in current_rows:
                return category_id
            if parent_id is not None and parent_id in current_rows:
                return parent_id
            return category_id

        def refund_envelope(category_id: int | None, parent_id: int | None, transaction_created_at: datetime | None) -> int | None:
            resolved = resolve_envelope(category_id, parent_id)
            if resolved is None:
                return None
            allocation = current_rows.get(resolved)
            if allocation is None:
                return None
            if transaction_created_at is None or allocation.created_at is None:
                return resolved
            return resolved if allocation.created_at <= transaction_created_at else None

        for tx in plain_by_month.get(key, []):
            if tx.amount_kzt is None:
                fx_incomplete = True
                continue
            if tx.type == TransactionType.EXPENSE and tx.category_id is not None:
                resolved = resolve_envelope(tx.category_id, tx.parent_id)
                if resolved is not None:
                    activity[resolved] -= tx.amount_kzt
            elif tx.type == TransactionType.INCOME:
                if tx.kind in {None, CategoryKind.INCOME}:
                    income += tx.amount_kzt
                elif tx.kind == CategoryKind.EXPENSE:
                    resolved = refund_envelope(tx.category_id, tx.parent_id, tx.created_at)
                    if resolved is not None:
                        activity[resolved] += tx.amount_kzt
                    else:
                        stray_refunds += tx.amount_kzt
                        if key == target and tx.category_id is not None:
                            target_stray_refunds[tx.category_id] += tx.amount_kzt

        for split in split_by_month.get(key, []):
            if split.amount_kzt is None:
                fx_incomplete = True
                continue
            if split.type == TransactionType.EXPENSE and split.category_id is not None:
                resolved = resolve_envelope(split.category_id, split.parent_id)
                if resolved is not None:
                    activity[resolved] -= split.amount_kzt

        cumulative_unassigned += income + stray_refunds - assigned
        category_ids = set(carry) | set(current_rows) | set(activity)
        next_carry: dict[int, Decimal] = defaultdict(lambda: ZERO)
        values: dict[int, dict] = {}
        for category_id in category_ids:
            row = current_rows.get(category_id)
            if row is not None:
                policy[category_id] = (row.rollover_positive, row.rollover_negative)
            rollover_positive, rollover_negative = policy[category_id]
            available = carry[category_id] + (row.assigned_amount if row else ZERO) + activity[category_id]
            values[category_id] = {
                "row": row,
                "activity": activity[category_id],
                "carried_in": carry[category_id],
                "available": available,
                "rollover_positive": rollover_positive,
                "rollover_negative": rollover_negative,
            }
            if (available > 0 and rollover_positive) or (available < 0 and rollover_negative):
                next_carry[category_id] = available
        carry = next_carry
        if key == target:
            target_values = values
            target_income = income
            target_assigned = assigned
            target_fx_incomplete = fx_incomplete

    items: list[EnvelopeItem] = []
    warnings: list[EnvelopeWarning] = []
    for category_id, values in target_values.items():
        category = category_by_id.get(category_id)
        if category is None:
            continue
        row = values["row"]
        planned = row.planned_amount if row else ZERO
        assigned_amount = row.assigned_amount if row else ZERO
        available = values["available"]
        is_unbudgeted = row is None
        items.append(
            EnvelopeItem(
                category_id=category_id,
                category_name=category.name,
                category_color=category.color,
                category_icon=category.icon,
                is_unbudgeted=is_unbudgeted,
                planned_amount=planned,
                assigned_amount=assigned_amount,
                activity=values["activity"],
                carried_in=values["carried_in"],
                available=available,
                is_overspent=available < 0,
                rollover_positive=values["rollover_positive"],
                rollover_negative=values["rollover_negative"],
                has_row=row is not None,
            )
        )
        if available < 0:
            warnings.append(EnvelopeWarning(code="overspent", category_id=category_id, amount=-available))
        if row is not None and assigned_amount < planned:
            warnings.append(EnvelopeWarning(code="underfunded", category_id=category_id, amount=planned - assigned_amount))
        if is_unbudgeted and values["activity"] < 0:
            warnings.append(EnvelopeWarning(code="unbudgeted_spending", category_id=category_id, amount=-values["activity"]))
    for category_id, amount in target_stray_refunds.items():
        warnings.append(EnvelopeWarning(code="refund_without_envelope", category_id=category_id, amount=amount))
    if cumulative_unassigned < 0:
        warnings.append(EnvelopeWarning(code="available_to_assign_negative", amount=-cumulative_unassigned))
    if target_fx_incomplete:
        warnings.append(EnvelopeWarning(code="fx_coverage_incomplete"))
    if income_before:
        warnings.append(
            EnvelopeWarning(
                code="income_before_tracking_start",
                amount=income_before,
                earliest_date=earliest_income_before.isoformat() if earliest_income_before else None,
            )
        )

    activity_total = sum((value["activity"] for value in target_values.values()), ZERO)
    has_drift = bool(target_row and target_row.is_closed and target_row.closed_activity_total != activity_total)
    if has_drift:
        warnings.append(
            EnvelopeWarning(
                code="closed_month_ledger_drift",
                amount=activity_total - (target_row.closed_activity_total or ZERO),
                closed_activity_total=target_row.closed_activity_total,
                current_activity_total=activity_total,
            )
        )
    items.sort(key=lambda item: (category_by_id[item.category_id].sort_order, item.category_id))
    return EnvelopeStatus(
        year=year,
        month=month,
        tracking_start=MonthRef(year=tracking_start[0], month=tracking_start[1]),
        is_closed=bool(target_row and target_row.is_closed),
        has_ledger_drift=has_drift,
        fx_incomplete=target_fx_incomplete,
        income=target_income,
        assigned=target_assigned,
        available_to_assign=cumulative_unassigned,
        items=items,
        warnings=warnings,
    )


async def set_allocation(
    session: AsyncSession,
    year: int,
    month: int,
    category_id: int,
    payload: EnvelopeAllocationInput,
    context: RequestWorkspace | None = None,
) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    await _expense_category(session, category_id, context)
    month_row = await _month_row(session, year, month, context)
    if month_row is None:
        month_row = EnvelopeMonth(year=year, month=month, workspace_id=None if context is None else context.workspace_id)
        session.add(month_row)
        await session.flush()
    elif month_row.is_closed:
        raise HTTPException(409, f"Envelope month {year}-{month:02d} is closed")
    allocation_stmt = select(EnvelopeAllocation).where(
        EnvelopeAllocation.year == year,
        EnvelopeAllocation.month == month,
        EnvelopeAllocation.category_id == category_id,
    )
    allocation_stmt = await _scoped(session, allocation_stmt, EnvelopeAllocation, context)
    allocation = (await session.execute(allocation_stmt)).scalar_one_or_none()
    old_assigned = allocation.assigned_amount if allocation else ZERO
    status = await get_status(session, year, month, context)
    delta = payload.assigned_amount - old_assigned
    if delta > ZERO and delta > status.available_to_assign:
        raise HTTPException(400, "Allocation exceeds money available to assign")
    if allocation is None:
        allocation = EnvelopeAllocation(
            year=year, month=month, category_id=category_id, workspace_id=None if context is None else context.workspace_id
        )
        session.add(allocation)
    allocation.assigned_amount = payload.assigned_amount
    if payload.planned_amount is not None:
        allocation.planned_amount = payload.planned_amount
    if payload.rollover_positive is not None:
        allocation.rollover_positive = payload.rollover_positive
    if payload.rollover_negative is not None:
        allocation.rollover_negative = payload.rollover_negative
    session.add(EnvelopeAuditLog(year=year, month=month, event_type="allocation", category_id=category_id, amount=delta))
    await session.commit()
    return await get_status(session, year, month, context)


async def delete_allocation(
    session: AsyncSession, year: int, month: int, category_id: int, context: RequestWorkspace | None = None
) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    await _require_open_month(session, year, month, context)
    allocation_stmt = select(EnvelopeAllocation).where(
        EnvelopeAllocation.year == year,
        EnvelopeAllocation.month == month,
        EnvelopeAllocation.category_id == category_id,
    )
    allocation_stmt = await _scoped(session, allocation_stmt, EnvelopeAllocation, context)
    allocation = (await session.execute(allocation_stmt)).scalar_one_or_none()
    if allocation is None:
        raise HTTPException(404, "Envelope allocation not found")
    amount = allocation.assigned_amount
    await session.delete(allocation)
    session.add(EnvelopeAuditLog(year=year, month=month, event_type="allocation", category_id=category_id, amount=-amount))
    await session.commit()
    return await get_status(session, year, month, context)


async def move(
    session: AsyncSession, year: int, month: int, payload: EnvelopeMoveInput, context: RequestWorkspace | None = None
) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    await _require_open_month(session, year, month, context)
    if payload.from_category_id == payload.to_category_id:
        raise HTTPException(400, "Envelope move needs two different categories")
    rows_stmt = select(EnvelopeAllocation).where(
        EnvelopeAllocation.year == year,
        EnvelopeAllocation.month == month,
        EnvelopeAllocation.category_id.in_([payload.from_category_id, payload.to_category_id]),
    )
    rows_stmt = await _scoped(session, rows_stmt, EnvelopeAllocation, context)
    rows = list((await session.execute(rows_stmt)).scalars())
    by_id = {row.category_id: row for row in rows}
    if len(by_id) != 2:
        raise HTTPException(404, "Both envelopes must exist before moving money")
    source = by_id[payload.from_category_id]
    target = by_id[payload.to_category_id]
    if source.assigned_amount < payload.amount:
        raise HTTPException(400, "Move exceeds source envelope assignment")
    source.assigned_amount -= payload.amount
    target.assigned_amount += payload.amount
    session.add(
        EnvelopeAuditLog(
            year=year,
            month=month,
            event_type="move",
            from_category_id=payload.from_category_id,
            to_category_id=payload.to_category_id,
            amount=payload.amount,
            note=payload.note,
        )
    )
    await session.commit()
    return await get_status(session, year, month, context)


async def apply_template(
    session: AsyncSession, year: int, month: int, template_id: int, context: RequestWorkspace | None = None
) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    await _require_open_month(session, year, month, context)
    template = await session.get(EnvelopeTemplate, template_id)
    if template is None:
        raise HTTPException(404, "Envelope template not found")
    items = list((await session.execute(select(EnvelopeTemplateItem).where(EnvelopeTemplateItem.template_id == template_id).order_by(EnvelopeTemplateItem.id))).scalars())
    total = ZERO
    for item in items:
        row_stmt = select(EnvelopeAllocation).where(
            EnvelopeAllocation.year == year,
            EnvelopeAllocation.month == month,
            EnvelopeAllocation.category_id == item.category_id,
        )
        row_stmt = await _scoped(session, row_stmt, EnvelopeAllocation, context)
        row = (await session.execute(row_stmt)).scalar_one_or_none()
        if row is None:
            row = EnvelopeAllocation(
                year=year,
                month=month,
                category_id=item.category_id,
                assigned_amount=ZERO,
                workspace_id=None if context is None else context.workspace_id,
            )
            session.add(row)
        row.planned_amount = item.planned_amount
        row.rollover_positive = item.rollover_positive
        row.rollover_negative = item.rollover_negative
        total += item.planned_amount
    session.add(EnvelopeAuditLog(year=year, month=month, event_type="template_applied", amount=total, note=template.name))
    await session.commit()
    return await get_status(session, year, month, context)


async def fund(
    session: AsyncSession, year: int, month: int, payload: EnvelopeFundInput, context: RequestWorkspace | None = None
) -> EnvelopeFundResult:
    if context is not None:
        context.require_mutation()
    await _require_open_month(session, year, month, context)
    if payload.template_id is not None:
        await apply_template(session, year, month, payload.template_id, context)
    if payload.copy_plan_from is not None:
        source_stmt = select(EnvelopeAllocation).where(
            EnvelopeAllocation.year == payload.copy_plan_from.year, EnvelopeAllocation.month == payload.copy_plan_from.month
        )
        source_stmt = await _scoped(session, source_stmt, EnvelopeAllocation, context)
        source_rows = list((await session.execute(source_stmt)).scalars())
        copied_total = ZERO
        for source in source_rows:
            target_stmt = select(EnvelopeAllocation).where(
                EnvelopeAllocation.year == year,
                EnvelopeAllocation.month == month,
                EnvelopeAllocation.category_id == source.category_id,
            )
            target_stmt = await _scoped(session, target_stmt, EnvelopeAllocation, context)
            target = (await session.execute(target_stmt)).scalar_one_or_none()
            if target is None:
                target = EnvelopeAllocation(
                    year=year,
                    month=month,
                    category_id=source.category_id,
                    assigned_amount=ZERO,
                    planned_amount=source.planned_amount,
                    rollover_positive=source.rollover_positive,
                    rollover_negative=source.rollover_negative,
                    workspace_id=None if context is None else context.workspace_id,
                )
                session.add(target)
                copied_total += source.planned_amount
            elif target.planned_amount == ZERO:
                target.planned_amount = source.planned_amount
                target.rollover_positive = source.rollover_positive
                target.rollover_negative = source.rollover_negative
                copied_total += source.planned_amount
        if copied_total:
            session.add(EnvelopeAuditLog(year=year, month=month, event_type="template_applied", amount=copied_total, note="copied plan"))
        await session.commit()
    status = await get_status(session, year, month, context)
    remaining = max(status.available_to_assign, ZERO)
    rows_stmt = select(EnvelopeAllocation).where(
        EnvelopeAllocation.year == year, EnvelopeAllocation.month == month
    ).order_by(EnvelopeAllocation.category_id)
    rows_stmt = await _scoped(session, rows_stmt, EnvelopeAllocation, context)
    rows = list((await session.execute(rows_stmt)).scalars())
    unfunded: list[EnvelopeShortfall] = []
    for row in rows:
        needed = max(row.planned_amount - row.assigned_amount, ZERO)
        delta = min(needed, remaining)
        if delta:
            row.assigned_amount += delta
            remaining -= delta
            session.add(EnvelopeAuditLog(year=year, month=month, event_type="allocation", category_id=row.category_id, amount=delta))
        shortfall = needed - delta
        if shortfall:
            unfunded.append(EnvelopeShortfall(category_id=row.category_id, shortfall=shortfall))
    await session.commit()
    return EnvelopeFundResult(status=await get_status(session, year, month, context), unfunded=unfunded)


async def fund_next_month(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeFundResult:
    if context is not None:
        context.require_mutation()
    await _require_open_month(session, year, month, context)
    next_year, next_month = _next_month((year, month))
    await open_month(session, next_year, next_month, context)
    return await fund(session, next_year, next_month, EnvelopeFundInput(copy_plan_from=MonthRef(year=year, month=month)), context)


async def close_month(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    row = await _month_row(session, year, month, context)
    if row is None:
        raise HTTPException(404, "Envelope month is not open")
    if row.is_closed:
        return await get_status(session, year, month, context)
    status = await get_status(session, year, month, context)
    total = sum((item.activity for item in status.items), ZERO)
    row.is_closed = True
    row.closed_at = datetime.now(timezone.utc)
    row.closed_activity_total = total
    session.add(EnvelopeAuditLog(year=year, month=month, event_type="month_closed", amount=total))
    await session.commit()
    return await get_status(session, year, month, context)


async def reopen_month(session: AsyncSession, year: int, month: int, context: RequestWorkspace | None = None) -> EnvelopeStatus:
    if context is not None:
        context.require_mutation()
    row = await _month_row(session, year, month, context)
    if row is None:
        raise HTTPException(404, "Envelope month is not open")
    if row.is_closed:
        row.is_closed = False
        row.closed_at = None
        row.closed_activity_total = None
        session.add(EnvelopeAuditLog(year=year, month=month, event_type="month_reopened", amount=ZERO))
        await session.commit()
    return await get_status(session, year, month, context)