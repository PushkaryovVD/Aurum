from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.categorization import (
    CategorizationMatchRead,
    CategorizationMatchRequest,
    CategorizationRuleCreate,
    CategorizationRuleRead,
    CategorizationRuleReorder,
    CategorizationRuleUpdate,
    RuleApplyResult,
)
from app.services.categorization_service import (
    apply_rules,
    create_rule,
    delete_rule,
    list_rules_read,
    match_for_transaction,
    reorder_rules,
    update_rule,
)

router = APIRouter(prefix="/categorization-rules", tags=["categorization"])


@router.get("", response_model=list[CategorizationRuleRead])
async def read_rules(session: AsyncSession = Depends(get_session)) -> list[CategorizationRuleRead]:
    """Every rule, enabled or not, in evaluation order."""
    return await list_rules_read(session)


@router.post("", response_model=CategorizationRuleRead, status_code=201)
async def create_rule_route(
    payload: CategorizationRuleCreate, session: AsyncSession = Depends(get_session)
) -> CategorizationRuleRead:
    return await create_rule(session, payload)


@router.post("/match", response_model=CategorizationMatchRead)
async def match_rule_route(
    payload: CategorizationMatchRequest, session: AsyncSession = Depends(get_session)
) -> CategorizationMatchRead:
    """Which rule would decide a transaction of this shape, and the category it
    would assign.

    The entry form asks this while the user types, so a category arrives with
    the reason attached instead of appearing by itself once the row is saved.
    """
    matched = await match_for_transaction(
        session,
        description=payload.description,
        merchant=payload.merchant,
        amount=payload.amount,
        currency=payload.currency,
        account_id=payload.account_id,
        transaction_type=payload.transaction_type,
    )
    if matched is None:
        return CategorizationMatchRead()
    return CategorizationMatchRead(
        rule_id=matched.id,
        rule_name=matched.name,
        category_id=matched.category_id,
        category_name=matched.category.name if matched.category else None,
        category_color=matched.category.color if matched.category else None,
    )


@router.post("/reorder", response_model=list[CategorizationRuleRead])
async def reorder_rule_route(
    payload: CategorizationRuleReorder, session: AsyncSession = Depends(get_session)
) -> list[CategorizationRuleRead]:
    """Replaces the whole order — first id runs first."""
    return await reorder_rules(session, payload)


@router.post("/apply", response_model=RuleApplyResult)
async def apply_rule_route(
    dry_run: bool = Query(default=True, description="Report what would change without writing it"),
    only_uncategorized: bool = Query(
        default=True, description="Leave transactions that already have a category alone"
    ),
    session: AsyncSession = Depends(get_session),
) -> RuleApplyResult:
    """Runs the saved rules over existing transactions.

    `dry_run` defaults to true on purpose: the only way to see what enabling or
    reordering a rule does is to ask first, and nothing in this endpoint changes
    history unless the caller says so explicitly.
    """
    return await apply_rules(session, dry_run=dry_run, only_uncategorized=only_uncategorized)


@router.patch("/{rule_id}", response_model=CategorizationRuleRead)
async def update_rule_route(
    rule_id: int, payload: CategorizationRuleUpdate, session: AsyncSession = Depends(get_session)
) -> CategorizationRuleRead:
    return await update_rule(session, rule_id, payload)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule_route(rule_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_rule(session, rule_id)
