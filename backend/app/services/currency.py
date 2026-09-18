"""Shared SQL expressions for reporting account-currency money in KZT."""
from sqlalchemy import case, func

from app.models.account import Account
from app.models.transaction import Transaction, TransactionSplit


def transaction_amount_kzt():
    return case(
        (Transaction.base_amount_kzt.is_not(None), Transaction.base_amount_kzt),
        (func.upper(Account.currency) == "KZT", Transaction.amount),
        else_=None,
    )


def split_amount_kzt():
    return case(
        (
            Transaction.exchange_rate_to_kzt.is_not(None),
            TransactionSplit.amount * Transaction.exchange_rate_to_kzt,
        ),
        (func.upper(Account.currency) == "KZT", TransactionSplit.amount),
        else_=None,
    )
