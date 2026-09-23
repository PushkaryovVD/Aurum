from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

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
    # `amount`/`account_currency` are the movement that changes the selected
    # account. `transaction_amount`/`currency` preserve the merchant-side
    # figure (for example 19.58 BYN charged as 2918.98 KZT).
    amount: Decimal = Field(gt=0)
    account_currency: str | None = Field(default=None, min_length=3, max_length=3)
    currency: str = Field(min_length=3, max_length=3)
    transaction_amount: Decimal | None = Field(default=None, gt=0)
    description: str
    details: str | None = None
    purpose: TransactionPurpose = TransactionPurpose.ORDINARY
    security_symbol: str | None = None
    # Chosen by the user in the preview; the parser never guesses one. Filled in
    # by the categorization rules when one matches (see `matched_rule`), and
    # left for the user to decide otherwise.
    category_id: int | None = None
    # The name of the rule that chose `category_id`, so the preview can say why
    # rather than just showing a category that appeared by itself. Informational
    # only — the commit reads `category_id`.
    matched_rule: str | None = None
    importable: bool = True
    warning: str | None = None

    @model_validator(mode="after")
    def fill_currency_defaults(self):
        # Backwards compatible with previews produced before statement rows
        # distinguished the account and purchase currencies.
        self.currency = self.currency.upper()
        self.account_currency = (self.account_currency or self.currency).upper()
        self.transaction_amount = self.transaction_amount or self.amount
        if self.account_currency == self.currency and self.transaction_amount != self.amount:
            raise ValueError("transaction_amount must equal amount when both currencies match")
        return self


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
