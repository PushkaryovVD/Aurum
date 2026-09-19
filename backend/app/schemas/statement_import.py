from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import TransactionPurpose, TransactionType


class StatementRow(BaseModel):
    source_row: str
    external_id: str
    date: date
    type: TransactionType
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    description: str
    details: str | None = None
    purpose: TransactionPurpose = TransactionPurpose.ORDINARY
    security_symbol: str | None = None
    importable: bool = True
    warning: str | None = None


class StatementPreview(BaseModel):
    provider: str
    file_name: str
    rows: list[StatementRow]
    warnings: list[str]


class StatementCommit(BaseModel):
    provider: str
    accounts_by_currency: dict[str, int]
    rows: list[StatementRow] = Field(min_length=1, max_length=5000)


class StatementCommitResult(BaseModel):
    created: int
    duplicates: int
    ignored: int
