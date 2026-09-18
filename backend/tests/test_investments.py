from httpx import AsyncClient

from tests.helpers import money


async def _security(client: AsyncClient) -> dict:
    account = (
        await client.post("/accounts", json={"name": "Broker cash", "type": "investment", "currency": "KZT"})
    ).json()
    portfolio_response = await client.post(
        "/investments/portfolios", json={"name": "Long term", "account_id": account["id"]}
    )
    assert portfolio_response.status_code == 201, portfolio_response.text
    security_response = await client.post(
        "/investments/securities",
        json={"portfolio_id": portfolio_response.json()["id"], "name": "Kazatomprom", "ticker": "KZAP", "currency": "KZT"},
    )
    assert security_response.status_code == 201, security_response.text
    return security_response.json()


async def test_weighted_cost_partial_sale_dividend_and_cash_links(client: AsyncClient):
    security = await _security(client)
    asset_id = security["asset_id"]
    first = await client.post(
        f"/investments/securities/{asset_id}/trades",
        json={"type": "buy", "quantity": "10", "price_per_unit": "100", "fee": "10", "date": "2026-01-01"},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/investments/securities/{asset_id}/trades",
        json={"type": "buy", "quantity": "10", "price_per_unit": "200", "fee": "10", "date": "2026-02-01"},
    )
    assert money(second.json()["average_cost"]) == money("151")

    sale = await client.post(
        f"/investments/securities/{asset_id}/trades",
        json={"type": "sell", "quantity": "5", "price_per_unit": "220", "fee": "5", "date": "2026-03-01"},
    )
    assert sale.status_code == 201, sale.text
    assert money(sale.json()["quantity"]) == money("15")
    assert money(sale.json()["realized_profit"]) == money("340")

    dividend = await client.post(
        f"/investments/securities/{asset_id}/dividends",
        json={"gross_amount": "100", "tax_amount": "15", "date": "2026-04-01", "external_id": "div-1"},
    )
    assert dividend.status_code == 201, dividend.text
    assert money(dividend.json()["net_dividends"]) == money("85")

    price = await client.put(
        f"/investments/securities/{asset_id}/price",
        json={"price_per_unit": "250", "as_of_date": "2026-04-01"},
    )
    assert price.status_code == 200, price.text
    body = price.json()
    assert money(body["current_value"]) == money("3750")
    assert money(body["unrealized_profit"]) == money("1485")
    assert money(body["total_return"]) == money("1910")

    transactions = (await client.get("/transactions", params={"page_size": 100})).json()["items"]
    purposes = [row["purpose"] for row in transactions]
    assert purposes.count("investment_trade") == 3
    assert purposes.count("fee") == 3
    assert purposes.count("dividend") == 1
    assert purposes.count("tax") == 1

    duplicate = await client.post(
        f"/investments/securities/{asset_id}/dividends",
        json={"gross_amount": "100", "date": "2026-04-01", "external_id": "div-1"},
    )
    assert duplicate.status_code == 409


async def test_deleting_trade_removes_generated_cash_movements(client: AsyncClient):
    security = await _security(client)
    response = await client.post(
        f"/investments/securities/{security['asset_id']}/trades",
        json={"type": "buy", "quantity": "2", "price_per_unit": "100", "fee": "5", "date": "2026-01-01"},
    )
    trade_id = response.json()["trades"][0]["id"]
    deleted = await client.delete(f"/investments/trades/{trade_id}")
    assert deleted.status_code == 200, deleted.text
    assert money(deleted.json()["quantity"]) == money("0")
    transactions = (await client.get("/transactions", params={"page_size": 100})).json()["items"]
    assert not transactions
