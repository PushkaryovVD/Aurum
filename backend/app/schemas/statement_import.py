from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import TransactionPurpose, TransactionType


class StatementRow(BaseModel):
    """One recognised movement, as it appears in the preview.

    Every field here is editable in the UI before commit — the parser's reading
    of a row is a proposal, not a verdict — so the commit payload is simply the
    user's corrected version of this list.
    """

    source_row: str
    # The bank's own operation id when the export carries one. Empty means the
    # export doesn't identify its rows; the service then derives a stable
    # content digest so a re-import is still recognised (see
    # services/statement_import_service._import_key).
    external_id: str = ""
    date: date
    type: TransactionType
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    description: str
    details: str | None = None
    purpose: TransactionPurpose = TransactionPurpose.ORDINARY
    security_symbol: str | None = None
    # Chosen by the user in the preview; the parser never guesses one.
    category_id: int | None = None
    importable: bool = True
    warning: str | None = None


class StatementPreview(BaseModel):
    provider: str
    # The adapter's human-readable name, so the UI can say which reader
    # recognised the file rather than showing a bare id.
    provider_label: str
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
