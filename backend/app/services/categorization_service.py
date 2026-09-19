"""Categorization rules: the matcher, plus CRUD and the previewed bulk apply.

The matcher is a pure function over a rule and a transaction's shape, so it can
be reused unchanged by the statement-import preview, the manual entry form and
the bulk apply — and tested without a database.

A rule is applied **when a transaction is created or previewed**, never as a
side effect of editing the rules. Changing history is a separate, explicitly
previewed action (`apply_rules` with dry_run=False).
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.categorization_rule import CategorizationRule
from app.models.enums import MatchType, TransactionType
from app.models.transaction import Transaction
from app.schemas.categorization import (
    CategorizationRuleCreate,
    CategorizationRuleRead,
    CategorizationRuleReorder,
    CategorizationRuleUpdate,
    RuleApplyResult,
    RuleEffectItem,
)

# Patterns run against a transaction's description/merchant only — a few hundred
# characters — but a pathological regex can still blow up on that, so the length
# is capped and a nested-quantifier shape is refused outright rather than left to
# hang a request thread.
MAX_PATTERN_LENGTH = 200
_NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*{]")
# How many example descriptions a rule's effect report carries.
SAMPLE_LIMIT = 3
# A bulk apply is bounded so one call can't walk an entire history.
MAX_APPLY_ROWS = 5000


def validate_pattern(match_type: MatchType, pattern: str) -> None:
    """Rejects a pattern that could never work — at save time, so a broken rule
    is a clear 422 rather than a rule that silently matches nothing forever."""
    if match_type is MatchType.REGEX:
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise HTTPException(422, f"A regular expression is limited to {MAX_PATTERN_LENGTH} characters")
        if _NESTED_QUANTIFIER.search(pattern):
            raise HTTPException(
                422, "Nested quantifiers are not allowed — they can make matching take exponential time"
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(422, f"Invalid regular expression: {exc}") from exc


@dataclass(frozen=True)
class CompiledRule:
    """A rule plus its compiled matcher — compiled once per run rather than per
    transaction, which is what keeps a 150-row import preview cheap."""

    rule: CategorizationRule
    pattern: re.Pattern[str]

    def matches(
        self,
        *,
        text: str,
        amount: Decimal,
        currency: str,
        account_id: int | None,
        transaction_type: TransactionType,
    ) -> bool:
        if not self.pattern.search(text):
            return False
        if self.rule.amount_min is not None and amount < self.rule.amount_min:
            return False
        if self.rule.amount_max is not None and amount > self.rule.amount_max:
            return False
        if self.rule.currency is not None and currency.upper() != self.rule.currency.upper():
            return False
        if self.rule.account_id is not None and account_id != self.rule.account_id:
            return False
        if self.rule.transaction_type is not None and transaction_type != self.rule.transaction_type:
            return False
        return True


def compile_rules(rules: list[CategorizationRule]) -> list[CompiledRule]:
    """The enabled rules, in priority order, ready to match."""
    compiled: list[CompiledRule] = []
    for rule in sorted(rules, key=lambda row: (row.priority, row.id)):
        if not rule.is_enabled:
            continue
        source = re.escape(rule.pattern) if rule.match_type is MatchType.CONTAINS else rule.pattern
        try:
            pattern = re.compile(source, re.IGNORECASE)
        except re.error:
            # A row stored before validation existed (or hand-edited) must not
            # take the whole run down with it.
            continue
        compiled.append(CompiledRule(rule=rule, pattern=pattern))
    return compiled


def match_rule(
    compiled: list[CompiledRule],
    *,
    description: str,
    merchant: str | None,
    amount: Decimal,
    currency: str,
    account_id: int | None,
    transaction_type: TransactionType,
) -> CategorizationRule | None:
    """The first enabled rule that matches, or None.

    Description and merchant are searched as one text: a bank export and a
    manual entry rarely agree on which of the two carries the shop name, and the
    user writing "Yandex Go" should not have to know which.
    """
    text = f"{description}\n{merchant or ''}"
    for candidate in compiled:
        if candidate.matches(
            text=text,
            amount=amount,
            currency=currency,
            account_id=account_id,
            transaction_type=transaction_type,
        ):
            return candidate.rule
    return None


def _to_read(rule: CategorizationRule) -> CategorizationRuleRead:
    return CategorizationRuleRead(
        id=rule.id,
        priority=rule.priority,
        is_enabled=rule.is_enabled,
        name=rule.name,
        match_type=rule.match_type,
        pattern=rule.pattern,
        amount_min=rule.amount_min,
        amount_max=rule.amount_max,
        currency=rule.currency,
        account_id=rule.account_id,
        transaction_type=rule.transaction_type,
        category_id=rule.category_id,
        category_name=rule.category.name if rule.category else None,
        category_color=rule.category.color if rule.category else None,
    )


async def list_rules(session: AsyncSession) -> list[CategorizationRule]:
    """Every rule, enabled or not, in the order they are evaluated — the list
    the UI shows and edits."""
    result = await session.execute(
        select(CategorizationRule)
        .options(selectinload(CategorizationRule.category))
        .order_by(CategorizationRule.priority, CategorizationRule.id)
    )
    return list(result.scalars().all())


async def list_rules_read(session: AsyncSession) -> list[CategorizationRuleRead]:
    return [_to_read(rule) for rule in await list_rules(session)]


async def _get_or_404(session: AsyncSession, rule_id: int) -> CategorizationRule:
    rule = await session.get(CategorizationRule, rule_id, options=[selectinload(CategorizationRule.category)])
    if rule is None:
        raise HTTPException(status_code=404, detail="Categorization rule not found")
    return rule


async def _reload(session: AsyncSession, rule: CategorizationRule) -> CategorizationRule:
    """Loads `category` on a rule that is already in the identity map.

    A `session.get` here would hand back the very instance just written — already
    present, so its loader options are ignored — and the first read of
    `rule.category` would then lazy-load outside the greenlet and raise
    MissingGreenlet. Refreshing the attribute is the idiom the rest of the
    codebase uses for exactly this (see `api/routes/assets.py`).
    """
    await session.refresh(rule, attribute_names=["category"])
    return rule


async def create_rule(session: AsyncSession, payload: CategorizationRuleCreate) -> CategorizationRuleRead:
    validate_pattern(payload.match_type, payload.pattern)
    highest = (await session.execute(select(func.max(CategorizationRule.priority)))).scalar_one()
    # New rules go last: an existing, more specific rule keeps winning until the
    # user deliberately moves the new one above it.
    rule = CategorizationRule(**payload.model_dump(), priority=(highest + 1) if highest is not None else 0)
    session.add(rule)
    await session.commit()
    return _to_read(await _reload(session, rule))


async def update_rule(
    session: AsyncSession, rule_id: int, payload: CategorizationRuleUpdate
) -> CategorizationRuleRead:
    rule = await _get_or_404(session, rule_id)
    updates = payload.model_dump(exclude_unset=True)
    match_type = updates.get("match_type", rule.match_type)
    pattern = updates.get("pattern", rule.pattern)
    validate_pattern(match_type, pattern)
    amount_min = updates.get("amount_min", rule.amount_min)
    amount_max = updates.get("amount_max", rule.amount_max)
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(422, "amount_min must not be greater than amount_max")
    for field, value in updates.items():
        setattr(rule, field, value)
    await session.commit()
    return _to_read(await _reload(session, rule))


async def delete_rule(session: AsyncSession, rule_id: int) -> None:
    rule = await _get_or_404(session, rule_id)
    await session.delete(rule)
    await session.commit()


async def reorder_rules(session: AsyncSession, payload: CategorizationRuleReorder) -> list[CategorizationRuleRead]:
    rules = await list_rules(session)
    known = {rule.id for rule in rules}
    if set(payload.ordered_ids) != known or len(payload.ordered_ids) != len(known):
        # A partial order has no defined meaning: the ids the caller left out
        # would end up somewhere arbitrary.
        raise HTTPException(422, "ordered_ids must list every existing rule exactly once")
    by_id = {rule.id: rule for rule in rules}
    for index, rule_id in enumerate(payload.ordered_ids):
        by_id[rule_id].priority = index
    await session.commit()
    return await list_rules_read(session)


async def apply_rules(
    session: AsyncSession,
    *,
    dry_run: bool,
    only_uncategorized: bool,
    limit: int = MAX_APPLY_ROWS,
) -> RuleApplyResult:
    """Runs the saved rules over existing transactions.

    `dry_run=True` (the default the API exposes) reports exactly what would
    happen and writes nothing. `only_uncategorized=False` re-decides rows that
    already have a category — the user's own correction included — so it is
    never the default.
    """
    rules = await list_rules(session)
    compiled = compile_rules(rules)

    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.account))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(min(limit, MAX_APPLY_ROWS))
    )
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    transactions = list((await session.execute(stmt)).scalars().all())

    counts: dict[int, int] = {rule.id: 0 for rule in rules}
    samples: dict[int, list[str]] = {rule.id: [] for rule in rules}
    written = 0
    for transaction in transactions:
        matched = match_rule(
            compiled,
            description=transaction.description,
            merchant=transaction.merchant,
            amount=transaction.amount,
            currency=transaction.currency,
            account_id=transaction.account_id,
            transaction_type=transaction.type,
        )
        if matched is None:
            continue
        counts[matched.id] += 1
        if len(samples[matched.id]) < SAMPLE_LIMIT:
            samples[matched.id].append(transaction.description)
        if not dry_run:
            transaction.category_id = matched.category_id
            written += 1

    if not dry_run and written:
        await session.commit()

    items = [
        RuleEffectItem(rule_id=rule.id, name=rule.name, matched=counts[rule.id], samples=samples[rule.id])
        for rule in rules
    ]
    return RuleApplyResult(
        dry_run=dry_run,
        considered=len(transactions),
        matched=sum(counts.values()),
        written=written,
        items=items,
    )
