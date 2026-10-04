from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.models.category import Category
from app.models.enums import CategoryKind
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


async def _validate_parent(
    session: AsyncSession,
    parent_id: int,
    kind: CategoryKind,
    category_id: int | None,
    context: RequestWorkspace,
) -> None:
    """Subcategories are one level deep only: a parent must itself be
    top-level, and must share the child's kind (an expense category can't
    nest under an income one, or vice versa)."""
    if parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent")
    parent_stmt = select(Category).where(Category.id == parent_id)
    if context.workspace_id is not None:
        parent_stmt = parent_stmt.where(Category.workspace_id == context.workspace_id)
    parent = (await session.execute(parent_stmt)).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=400, detail="Parent category not found")
    if parent.parent_id is not None:
        raise HTTPException(status_code=400, detail="Subcategories can only be one level deep")
    if parent.kind != kind:
        raise HTTPException(status_code=400, detail="A subcategory must have the same kind as its parent")


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    kind: CategoryKind | None = None,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> list[Category]:
    stmt = select(Category).order_by(Category.sort_order)
    if context.workspace_id is not None:
        stmt = stmt.where(Category.workspace_id == context.workspace_id)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> Category:
    context.require_mutation()
    if payload.parent_id is not None:
        await _validate_parent(session, payload.parent_id, payload.kind, category_id=None, context=context)
    category = Category(**payload.model_dump(), is_default=False, workspace_id=context.workspace_id)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> Category:
    context.require_mutation()
    category_stmt = select(Category).where(Category.id == category_id)
    if context.workspace_id is not None:
        category_stmt = category_stmt.where(Category.workspace_id == context.workspace_id)
    category = (await session.execute(category_stmt)).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"] is not None:
        await _validate_parent(session, updates["parent_id"], category.kind, category_id=category_id, context=context)
        has_children = (
            await session.execute(
                select(Category.id)
                .where(Category.parent_id == category_id)
                .where(Category.workspace_id == context.workspace_id if context.workspace_id is not None else True)
                .limit(1)
            )
        ).first()
        if has_children is not None:
            raise HTTPException(status_code=400, detail="A category with subcategories cannot become a subcategory itself")
    for field, value in updates.items():
        setattr(category, field, value)
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> None:
    context.require_mutation()
    category_stmt = select(Category).where(Category.id == category_id)
    if context.workspace_id is not None:
        category_stmt = category_stmt.where(Category.workspace_id == context.workspace_id)
    category = (await session.execute(category_stmt)).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_default:
        # A default (seeded) category can be removed once it's unused — but
        # never while transactions still point at it, or a whole year's
        # worth of history would silently lose its category (the FK is
        # ON DELETE SET NULL, so nothing would error, it would just vanish
        # from every report). A custom category has no such guard: the user
        # created it and can freely delete it, same as before.
        has_transaction = (
            await session.execute(select(Transaction.id).where(Transaction.category_id == category_id).limit(1))
        ).first()
        has_split = (
            await session.execute(select(TransactionSplit.id).where(TransactionSplit.category_id == category_id).limit(1))
        ).first()
        if has_transaction is not None or has_split is not None:
            raise HTTPException(
                status_code=400, detail="Default categories can only be deleted once they have no transactions"
            )
    await session.delete(category)
    await session.commit()
