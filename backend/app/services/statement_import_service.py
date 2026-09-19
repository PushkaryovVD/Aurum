"""Statement import: the write half of the pipeline.

Parsing lives in app/importers (one adapter per bank, see base.py). This module
owns what happens after the user has reviewed the preview: turning confirmed
rows into transactions atomically, idempotently, and with the same currency
semantics as manual entry.
"""
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_destructive
from app.models.account import Account
from app.models.enums import ExchangeRateSource
from app.models.transaction import Transaction
from app.schemas.statement_import import StatementCommit, StatementCommitResult, StatementRow
from app.services.exchange_rate_service import get_exchange_rate


def _import_key(row: StatementRow) -> str:
    """The identity a row is stored under, and the thing a re-import is matched
    on.

    A bank that supplies an operation id gets it verbatim — exact, and the
    reason re-uploading the same Tradernet statement is a no-op. An export that
    doesn't identify its rows falls back to a digest of the row's own content
    (date, direction, amount, currency, description), which stays stable across
    uploads of the same statement.

    The trade-off is deliberate: two genuinely identical movements on the same
    day are indistinguishable from each other, so the second is reported as a
    duplicate rather than silently added. A row the user edits in the preview
    before committing therefore gets a different key than the one the parser
    proposed — which is what should happen, since it is no longer that row.
    """
    if row.external_id:
        return row.external_id
    digest = sha256(
        "|".join(
            [row.date.isoformat(), row.type.value, str(row.amount), row.currency.upper(), row.description]
        ).encode()
    ).hexdigest()
    return f"auto:{digest[:40]}"


async def _rate_snapshot(
    session: AsyncSession, row: StatementRow
) -> tuple[Decimal | None, ExchangeRateSource | None]:
    """The KZT conversion snapshot for one row.

    The official NBK rate for the row's own date is cached and used. When the
    rate service is unreachable the row is still imported, just without a KZT
    figure — exactly what manual entry does, because a missing rate must never
    cost the user a transaction.
    """
    if row.currency.upper() == "KZT":
        return Decimal("1"), ExchangeRateSource.NBK
    try:
        official = await get_exchange_rate(session, row.date, row.currency)
    except HTTPException as exc:
        if exc.status_code not in {422, 503}:
            raise
        return None, None
    return official.rate_to_kzt, ExchangeRateSource.NBK


async def _destination_accounts(session: AsyncSession, payload: StatementCommit) -> dict[str, Account]:
    """The account each currency's rows go to, validated to actually be
    denominated in that currency — the ledger currency of an imported row is
    its account's, same rule as the transactions API."""
    accounts: dict[str, Account] = {}
    for currency, account_id in payload.accounts_by_currency.items():
        account = await session.get(Account, account_id)
        if account is None:
            raise HTTPException(400, f"Unknown account for {currency}")
        if account.currency.upper() != currency.upper():
            raise HTTPException(422, f"Account {account.name} is not denominated in {currency.upper()}")
        accounts[currency.upper()] = account
    return accounts


async def commit_statement(session: AsyncSession, payload: StatementCommit) -> StatementCommitResult:
    """Writes the rows the user confirmed in the preview.

    Idempotent by construction: a row whose key already exists on its
    destination account is counted as a duplicate and skipped, so re-uploading
    the same statement adds nothing.

    The duplicate check is grouped by destination account because that is what
    the database's own uniqueness rule is — (account_id, external_id). Treating
    an operation id as globally unique would silently drop a legitimate second
    import of the same document into a different account.
    """
    importable = [row for row in payload.rows if row.importable]
    accounts = await _destination_accounts(session, payload)

    rows_by_account: dict[int, list[StatementRow]] = defaultdict(list)
    for row in importable:
        account = accounts.get(row.currency.upper())
        if account is None:
            raise HTTPException(422, f"No destination account selected for {row.currency.upper()}")
        rows_by_account[account.id].append(row)

    created = 0
    duplicates = 0
    for account_id, rows in rows_by_account.items():
        keys = [_import_key(row) for row in rows]
        seen = set(
            (
                await session.execute(
                    select(Transaction.external_id).where(
                        Transaction.account_id == account_id, Transaction.external_id.in_(keys)
                    )
                )
            )
            .scalars()
            .all()
        )
        for row, key in zip(rows, keys):
            if key in seen:
                duplicates += 1
                continue
            # Also catches the same row appearing twice in one payload — the
            # query above can't see that, because nothing is flushed yet.
            seen.add(key)
            rate, source = await _rate_snapshot(session, row)
            session.add(
                Transaction(
                    account_id=account_id,
                    category_id=row.category_id,
                    type=row.type,
                    # The destination account was required to match the row's
                    # currency above, so the account-side debit and the
                    # transaction's own amount are the same figure here.
                    amount=row.amount,
                    currency=row.currency.upper(),
                    transaction_amount=row.amount,
                    exchange_rate_to_kzt=rate,
                    base_amount_kzt=(row.amount * rate).quantize(Decimal("0.01")) if rate is not None else None,
                    exchange_rate_source=source,
                    external_id=key,
                    purpose=row.purpose,
                    description=row.description,
                    notes=row.details,
                    date=row.date,
                )
            )
            created += 1

    await session.commit()
    # One request can add hundreds of rows from a document — worth a line so an
    # unexpected pile of transactions can be dated back to the file it came from.
    log_destructive("statement.imported", provider=payload.provider, created=created, duplicates=duplicates)
    return StatementCommitResult(
        created=created, duplicates=duplicates, ignored=len(payload.rows) - len(importable)
    )
