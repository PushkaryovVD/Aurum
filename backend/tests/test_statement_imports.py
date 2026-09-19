"""Bank statement import: parsing, previewing, and the commit that follows.

The pipeline the tests pin down is parse -> preview/edit -> validate -> commit:
nothing is written to the ledger until the user confirms, and re-uploading the
same document adds nothing.
"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from httpx import AsyncClient
from openpyxl import Workbook

from app.services import statement_import_service
from tests.helpers import money

HEADER = ["Операция №", "Дата", "Операция", "Комментарий", "Сумма", "Валюта"]


def _workbook(rows: list[list]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "sheet"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _tradernet_file() -> bytes:
    return _workbook(
        [
            [101, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге (Issuer (TEST.KZ))", 1250, "KZT"],
            [102, datetime(2026, 9, 18), "Купон", "Купон по бумаге (Bond (BOND.AIX.KZ))", 10, "USD"],
            [103, datetime(2026, 9, 18), "Блокировка", "Temporary", -10, "USD"],
        ]
    )


def _rate(value: str):
    """A stand-in for the NBK lookup, so the import tests never touch the
    network and the KZT snapshot is a known number."""

    async def lookup(*args, **kwargs):
        return SimpleNamespace(rate_to_kzt=Decimal(value))

    return lookup


async def _preview(client: AsyncClient, content: bytes | None = None):
    return await client.post(
        "/statement-imports/preview", files={"file": ("tradernet.xlsx", content or _tradernet_file())}
    )


async def test_tradernet_preview_recognizes_income_and_ignored_rows(client: AsyncClient):
    response = await _preview(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "tradernet"
    assert body["provider_label"] == "Tradernet Global / Freedom Broker"
    assert [row["purpose"] for row in body["rows"][:2]] == ["dividend", "coupon"]
    assert body["rows"][0]["security_symbol"] == "TEST.KZ"
    assert body["rows"][2]["importable"] is False


async def test_preview_writes_nothing_to_the_ledger(client: AsyncClient):
    """The whole point of the preview step: reading a document must not post a
    single transaction."""
    before = (await client.get("/transactions")).json()["total"]

    assert (await _preview(client)).status_code == 200

    assert (await client.get("/transactions")).json()["total"] == before


async def test_excel_serial_dates_are_recognized(client: AsyncClient):
    """The real export writes its date column as a bare Excel serial number
    unless the cell happens to carry a date format. A parser that only accepts
    datetimes skips every row of the actual file instead of failing loudly."""
    content = _workbook([[201, 45247.43127314815, "Дивиденды", "(Issuer (TEST.KZ))", 100, "KZT"]])

    body = (await _preview(client, content)).json()

    assert [row["date"] for row in body["rows"]] == ["2023-11-17"]


async def test_reversed_operation_takes_its_direction_from_the_amount(client: AsyncClient):
    """"Reverted: Купон …" arrives as a negative coupon. Reading the operation
    name alone would book it as income and overstate the balance."""
    content = _workbook([[301, datetime(2026, 9, 18), "Купон", "Reverted: Купон по бумаге", -9, "USD"]])

    body = (await _preview(client, content)).json()

    row = body["rows"][0]
    assert row["type"] == "expense"
    assert row["purpose"] == "coupon"
    assert money(row["amount"]) == Decimal("9")


async def test_unrecognized_document_is_rejected_without_crashing(client: AsyncClient):
    response = await client.post(
        "/statement-imports/preview", files={"file": ("broken.xlsx", b"this is not a workbook")}
    )
    assert response.status_code == 422


async def test_unsupported_file_type_names_what_is_supported(client: AsyncClient):
    response = await client.post("/statement-imports/preview", files={"file": ("statement.csv", b"a,b")})
    assert response.status_code == 422
    assert ".xlsx" in response.json()["detail"]


async def test_tradernet_commit_is_atomic_and_idempotent(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    usd = (
        await client.post("/accounts", json={"name": "Broker USD", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    payload = {
        "provider": "tradernet",
        "accounts_by_currency": {"KZT": kzt["id"], "USD": usd["id"]},
        "rows": preview["rows"],
    }

    first = await client.post("/statement-imports/commit", json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 2, "duplicates": 0, "ignored": 1}

    second = await client.post("/statement-imports/commit", json=payload)
    assert second.status_code == 200
    assert second.json() == {"created": 0, "duplicates": 2, "ignored": 1}


async def test_commit_stores_the_transaction_currency(client: AsyncClient, monkeypatch):
    """The regression this whole milestone exists for: an imported row must
    carry the currency fields the multicurrency ledger made mandatory."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    usd = (
        await client.post("/accounts", json={"name": "Broker USD", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    payload = {
        "provider": "tradernet",
        "accounts_by_currency": {"KZT": kzt["id"], "USD": usd["id"]},
        "rows": preview["rows"],
    }

    assert (await client.post("/statement-imports/commit", json=payload)).status_code == 200

    usd_items = (await client.get("/transactions", params={"account_id": usd["id"]})).json()["items"]
    assert len(usd_items) == 1
    assert usd_items[0]["currency"] == "USD"
    assert money(usd_items[0]["transaction_amount"]) == Decimal("10.00")
    # The destination account is denominated in USD, so the account-side debit
    # and the transaction's own amount are the same figure.
    assert money(usd_items[0]["amount"]) == Decimal("10.00")
    assert money(usd_items[0]["base_amount_kzt"]) == Decimal("5000.00")


async def test_same_statement_into_a_second_account_is_not_treated_as_a_duplicate(
    client: AsyncClient, monkeypatch
):
    """Duplicate detection is (account, operation id), matching the database's
    own unique constraint — an operation id is not globally unique, so treating
    it as such would silently drop a legitimate second import."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    usd_first = (
        await client.post("/accounts", json={"name": "Broker A", "type": "investment", "currency": "USD"})
    ).json()
    usd_second = (
        await client.post("/accounts", json={"name": "Broker B", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    usd_rows = [row for row in preview["rows"] if row["currency"] == "USD"]

    first = await client.post(
        "/statement-imports/commit",
        json={"provider": "tradernet", "accounts_by_currency": {"USD": usd_first["id"]}, "rows": usd_rows},
    )
    second = await client.post(
        "/statement-imports/commit",
        json={"provider": "tradernet", "accounts_by_currency": {"USD": usd_second["id"]}, "rows": usd_rows},
    )

    assert first.json()["created"] == 1
    # The USD rows are the coupon plus the reservation, which is never posted.
    assert second.json() == {"created": 1, "duplicates": 0, "ignored": 1}


async def test_rows_without_an_operation_id_deduplicate_by_content(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    content = _workbook([["", datetime(2026, 9, 18), "Карточный платеж", "Пополнение счёта картой", 5000, "KZT"]])
    preview = (await _preview(client, content)).json()
    assert preview["rows"][0]["external_id"] == ""
    payload = {"provider": "tradernet", "accounts_by_currency": {"KZT": kzt["id"]}, "rows": preview["rows"]}

    assert (await client.post("/statement-imports/commit", json=payload)).json()["created"] == 1
    assert (await client.post("/statement-imports/commit", json=payload)).json()["duplicates"] == 1

    stored = (await client.get("/transactions")).json()["items"][0]
    assert stored["external_id"].startswith("auto:")


async def test_edits_made_in_the_preview_are_what_gets_stored(
    client: AsyncClient, monkeypatch, categories
):
    """The parser's reading is a proposal: whatever the user corrects before
    pressing import is what must land in the ledger."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    content = _workbook([["", datetime(2026, 9, 18), "Карточный платеж", "Пополнение", 5000, "KZT"]])
    rows = (await _preview(client, content)).json()["rows"]

    groceries = categories["Groceries"]["id"]
    rows[0] = {
        **rows[0],
        "description": "Продукты",
        "amount": "750.00",
        "type": "expense",
        "category_id": groceries,
    }
    payload = {"provider": "tradernet", "accounts_by_currency": {"KZT": kzt["id"]}, "rows": rows}
    assert (await client.post("/statement-imports/commit", json=payload)).status_code == 200

    stored = (await client.get("/transactions")).json()["items"][0]
    assert stored["description"] == "Продукты"
    assert money(stored["amount"]) == Decimal("750.00")
    assert stored["type"] == "expense"
    assert stored["category_id"] == groceries
