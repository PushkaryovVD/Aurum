from datetime import datetime
from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace

from httpx import AsyncClient
from openpyxl import Workbook
from app.services import statement_import_service


def _tradernet_file() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "sheet"
    sheet.append(["Операция №", "Дата", "Операция", "Комментарий", "Сумма", "Валюта"])
    sheet.append([101, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге (Issuer (TEST.KZ))", 1250, "KZT"])
    sheet.append([102, datetime(2026, 9, 18), "Купон", "Купон по бумаге (Bond (BOND.AIX.KZ))", 10, "USD"])
    sheet.append([103, datetime(2026, 9, 18), "Блокировка", "Temporary", -10, "USD"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


async def test_tradernet_preview_recognizes_income_and_ignored_rows(client: AsyncClient):
    response = await client.post(
        "/statement-imports/preview",
        files={"file": ("tradernet.xlsx", _tradernet_file(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "tradernet"
    assert [row["purpose"] for row in body["rows"][:2]] == ["dividend", "coupon"]
    assert body["rows"][0]["security_symbol"] == "TEST.KZ"
    assert body["rows"][2]["importable"] is False


async def test_tradernet_commit_is_atomic_and_idempotent(client: AsyncClient, monkeypatch):
    async def rate(*args, **kwargs):
        return SimpleNamespace(rate_to_kzt=Decimal("500"))

    monkeypatch.setattr(statement_import_service, "get_exchange_rate", rate)
    kzt = (await client.get("/accounts")).json()[0]
    usd_response = await client.post("/accounts", json={"name": "Broker USD", "type": "investment", "currency": "USD"})
    usd = usd_response.json()
    preview = (
        await client.post("/statement-imports/preview", files={"file": ("tradernet.xlsx", _tradernet_file())})
    ).json()
    payload = {"provider": "tradernet", "accounts_by_currency": {"KZT": kzt["id"], "USD": usd["id"]}, "rows": preview["rows"]}
    first = await client.post("/statement-imports/commit", json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 2, "duplicates": 0, "ignored": 1}
    second = await client.post("/statement-imports/commit", json=payload)
    assert second.status_code == 200
    assert second.json() == {"created": 0, "duplicates": 2, "ignored": 1}
