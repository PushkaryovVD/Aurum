"""Freedom Bank Kazakhstan card-statement text PDFs (Russian 2026 layout)."""
import re
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from app.importers.base import StatementImporter
from app.importers.pdf_text import extract_pdf_pages
from app.models.enums import TransactionPurpose, TransactionType
from app.schemas.statement_import import StatementPreview, StatementRow

_DATE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})(?:\s+(.*))?$")
_MOVEMENT = re.compile(r"^([+-])\s*([\d,]+\.\d{2})\s+(?:[$₸]\s+)?([A-Z]{3})\s+(.+)$")


class FreedomBankPdfImporter(StatementImporter):
    id = "freedom_bank_pdf"
    label = "Freedom Bank Kazakhstan PDF"
    extensions = (".pdf",)

    def parse(self, file_name: str, content: bytes) -> StatementPreview:
        return self.parse_pages(file_name, extract_pdf_pages(content))

    def parse_pages(self, file_name: str, pages: list[str]) -> StatementPreview:
        text = "\n".join(pages)
        if "Фридом Банк Казахстан" not in text or "Выписка по карте" not in text:
            raise HTTPException(422, "Not a supported Freedom Bank card statement")
        lines = [(page_no, line.strip()) for page_no, page in enumerate(pages, 1) for line in page.splitlines()]
        rows: list[StatementRow] = []
        index = 0
        while index < len(lines):
            page_no, line = lines[index]
            date_match = _DATE.match(line)
            if not date_match:
                index += 1
                continue
            raw_date, tail = date_match.groups()
            pieces = [tail] if tail else []
            cursor = index + 1
            while cursor < len(lines) and not _DATE.match(lines[cursor][1]):
                candidate = lines[cursor][1]
                if candidate.startswith(("Итого", "Дата Сумма", "АО ")):
                    break
                if candidate.startswith("Сумма в обработке.") and "Банк ожидает" in candidate:
                    break
                if candidate:
                    pieces.append(candidate)
                cursor += 1
            joined = " ".join(piece for piece in pieces if piece)
            movement = _MOVEMENT.match(joined)
            if movement:
                sign, raw_amount, currency, description = movement.groups()
                amount = Decimal(raw_amount.replace(",", ""))
                pending = description.startswith("Сумма в обработке")
                operation, _, details = description.partition(" ")
                if description.startswith("Сумма в обработке"):
                    operation = "Сумма в обработке"
                    details = description[len(operation):].strip()
                elif description.startswith("Пополнение"):
                    operation = "Пополнение"
                    details = description[len(operation):].strip()
                rows.append(
                    StatementRow(
                        source_row=f"page {page_no}, operation {len(rows) + 1}",
                        date=datetime.strptime(raw_date, "%d.%m.%Y").date(),
                        type=TransactionType.INCOME if sign == "+" else TransactionType.EXPENSE,
                        amount=amount,
                        account_currency=currency,
                        currency=currency,
                        transaction_amount=amount,
                        description=operation,
                        details=details or None,
                        purpose=TransactionPurpose.ORDINARY,
                        importable=not pending,
                        warning="Pending card amount is not a posted movement" if pending else None,
                    )
                )
            index = max(cursor, index + 1)
        if not rows:
            raise HTTPException(422, "Freedom Bank operation table was not found")
        return StatementPreview(
            provider=self.id,
            provider_label=self.label,
            file_name=file_name,
            rows=rows,
            warnings=["Statement contains pending amounts; they remain visible but are not imported"]
            if any(not row.importable for row in rows)
            else [],
        )
