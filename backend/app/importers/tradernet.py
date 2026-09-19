"""Tradernet Global / Freedom Broker cash-movement XLSX statements.

One row per cash movement, each carrying a stable operation number — which
makes this the one format here that de-duplicates exactly instead of by
content digest.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from fastapi import HTTPException
from openpyxl import load_workbook

from app.importers.base import StatementImporter
from app.models.enums import TransactionPurpose, TransactionType
from app.schemas.statement_import import StatementPreview, StatementRow

# The sheet header this adapter understands, exactly as the export writes it.
# A workbook whose header differs is rejected rather than half-read.
HEADERS = ("Операция №", "Дата", "Операция", "Комментарий", "Сумма", "Валюта")

# The instrument a comment refers to, e.g. "(HSBK.KZ)" or
# "(FFSPC1.1228.AIX.KZ)" — the export's own shorthand for the ticker.
_SYMBOL = re.compile(r"\(([A-Z0-9][A-Z0-9.]{1,40})\)\)")

# Excel counts days from 1899-12-30 (not 1900-01-01) because of its
# long-standing leap-year bug; this epoch is the one that yields the right date.
_EXCEL_EPOCH = datetime(1899, 12, 30)

# Operation name -> (purpose, whether it is a real cash movement, why not when
# it isn't). The *direction* is deliberately not in this table — it comes from
# the amount's sign, because a corrected or reversed entry arrives as a
# negative row of an otherwise incoming operation ("Reverted: Купон …", -9 USD)
# and reading the name alone would book it as income.
_OPERATIONS: dict[str, tuple[TransactionPurpose, bool, str | None]] = {
    "дивиденды": (TransactionPurpose.DIVIDEND, True, None),
    "купон": (TransactionPurpose.COUPON, True, None),
    "комиссия за сделки": (TransactionPurpose.FEE, True, None),
    "налоги": (TransactionPurpose.TAX, True, None),
    "карточный платеж": (TransactionPurpose.ORDINARY, True, None),
    # A reservation is not a posted movement — the money never left.
    "блокировка": (TransactionPurpose.ORDINARY, False, "Temporary reservation is not a posted cash movement"),
    "разблокировка": (TransactionPurpose.ORDINARY, False, "Temporary reservation is not a posted cash movement"),
    # The principal of a trade is booked from the trades report instead, so
    # importing the settlement row as well would double it.
    "оплата по сделке": (
        TransactionPurpose.INVESTMENT_TRADE,
        False,
        "Trade settlement needs the broker trades report to avoid duplicate principal",
    ),
    # Both sides live in this same statement, under the same account.
    "перевод внутри компании": (
        TransactionPurpose.ORDINARY,
        False,
        "Internal transfer needs both source and destination accounts",
    ),
}


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _symbol(comment: str) -> str | None:
    match = _SYMBOL.search(comment)
    return match.group(1) if match else None


def _classify(operation: str, amount: Decimal) -> tuple[TransactionType, TransactionPurpose, bool, str | None]:
    purpose, importable, warning = _OPERATIONS.get(
        operation.strip().casefold(), (TransactionPurpose.ORDINARY, True, None)
    )
    tx_type = TransactionType.INCOME if amount >= 0 else TransactionType.EXPENSE
    return tx_type, purpose, importable, warning


def _event_date(raw) -> date:
    """Excel hands the date back as a datetime when the cell carries a date
    format and as a bare serial number when it doesn't — this export does both,
    depending on how the row was written. A text date is the last fallback."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = _text(raw)
    try:
        serial = float(text)
    except ValueError:
        return datetime.strptime(text, "%d.%m.%Y").date()
    return (_EXCEL_EPOCH + timedelta(days=serial)).date()


class TradernetImporter(StatementImporter):
    id = "tradernet"
    label = "Tradernet Global / Freedom Broker"
    extensions = (".xlsx",)

    def parse(self, file_name: str, content: bytes) -> StatementPreview:
        try:
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise HTTPException(422, "The XLSX file could not be opened") from exc

        rows: list[StatementRow] = []
        warnings: list[str] = []
        matched_sheet = False
        for sheet in workbook.worksheets:
            iterator = sheet.iter_rows(values_only=True)
            header = next(iterator, None)
            if not header or tuple(_text(value) for value in header[:6]) != HEADERS:
                warnings.append(f"{sheet.title}: unsupported header row")
                continue
            matched_sheet = True
            for row_number, values in enumerate(iterator, start=2):
                if not any(value is not None for value in values):
                    continue
                try:
                    rows.append(self._row(sheet.title, row_number, values))
                except (ValueError, InvalidOperation, TypeError) as exc:
                    warnings.append(f"{sheet.title}!{row_number}: {exc}")
        if not matched_sheet:
            raise HTTPException(422, "No Tradernet cash-movement sheet was recognized")
        return StatementPreview(
            provider=self.id, provider_label=self.label, file_name=file_name, rows=rows, warnings=warnings
        )

    @staticmethod
    def _row(sheet_title: str, row_number: int, values: tuple) -> StatementRow:
        operation_id, raw_date, operation, comment, raw_amount, currency = values[:6]
        event_date = _event_date(raw_date)
        amount = Decimal(str(raw_amount))
        if amount == 0:
            raise ValueError("zero amount")
        operation_text = _text(operation)
        tx_type, purpose, importable, warning = _classify(operation_text, amount)
        details = _text(comment)
        operation_id = _text(operation_id)
        return StatementRow(
            source_row=f"{sheet_title}!{row_number}",
            # The broker's own operation number — the exact identity a re-import
            # is matched on, so the same statement can be uploaded twice safely.
            # Left empty when the export has no number for the row, which makes
            # the service fall back to a content digest instead of inventing an
            # id that every unnumbered row would then share.
            external_id=f"tradernet:{operation_id}" if operation_id else "",
            date=event_date,
            type=tx_type,
            amount=abs(amount),
            currency=_text(currency).upper(),
            description=operation_text,
            details=details or None,
            purpose=purpose,
            security_symbol=_symbol(details),
            importable=importable,
            warning=warning,
        )
