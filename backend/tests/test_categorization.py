"""Categorization rules: ordering, validation, and what they do to an import
preview and to transactions that already exist."""
from datetime import datetime
from io import BytesIO

from httpx import AsyncClient
from openpyxl import Workbook

from tests.helpers import txn_payload as _txn

HEADER = ["Операция №", "Дата", "Операция", "Комментарий", "Сумма", "Валюта"]


def _workbook(rows: list[list]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


async def _preview(client: AsyncClient, content: bytes):
    return await client.post("/statement-imports/preview", files={"file": ("tradernet.xlsx", content)})


async def _rule(client: AsyncClient, *, category_id: int, pattern: str, name: str = "Rule", **overrides):
    return await client.post(
        "/categorization-rules", json={"name": name, "pattern": pattern, "category_id": category_id, **overrides}
    )


async def test_rules_are_listed_in_evaluation_order(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="First", pattern="a", category_id=groceries)
    await _rule(client, name="Second", pattern="b", category_id=groceries)

    listed = (await client.get("/categorization-rules")).json()

    assert [rule["name"] for rule in listed] == ["First", "Second"]
    assert [rule["priority"] for rule in listed] == [0, 1]
    assert listed[0]["category_name"] == "Groceries"


async def test_reorder_replaces_the_whole_order(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    first = (await _rule(client, name="First", pattern="a", category_id=groceries)).json()
    second = (await _rule(client, name="Second", pattern="b", category_id=groceries)).json()

    resp = await client.post("/categorization-rules/reorder", json={"ordered_ids": [second["id"], first["id"]]})
    assert resp.status_code == 200
    assert [rule["name"] for rule in resp.json()] == ["Second", "First"]

    # A partial order has no defined meaning — the ids left out would land
    # somewhere arbitrary — so it is refused rather than guessed at.
    partial = await client.post("/categorization-rules/reorder", json={"ordered_ids": [second["id"]]})
    assert partial.status_code == 422


async def test_an_invalid_regex_is_refused_at_save_time(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]

    assert (
        await _rule(client, pattern="(unclosed", match_type="regex", category_id=groceries)
    ).status_code == 422
    # A nested quantifier can make matching take exponential time even on a
    # short subject, so it never reaches the database.
    assert (
        await _rule(client, pattern="(a+)+$", match_type="regex", category_id=groceries)
    ).status_code == 422


async def test_amount_bounds_must_be_ordered(client: AsyncClient, categories):
    resp = await _rule(
        client, pattern="x", category_id=categories["Groceries"]["id"], amount_min="100", amount_max="10"
    )
    assert resp.status_code == 422


async def test_the_first_matching_rule_wins(client: AsyncClient, categories):
    """Order is the feature: a broad rule created first keeps winning until the
    user deliberately moves the specific one above it."""
    transport = categories["Transportation"]["id"]
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=transport)
    await _rule(client, name="Яндекс Go", pattern="яндекс го", category_id=groceries)

    body = (
        await _preview(
            client, _workbook([[1, datetime(2026, 9, 18), "Карточный платеж", "Яндекс Go поездка", 900, "KZT"]])
        )
    ).json()

    assert body["rows"][0]["category_id"] == transport
    assert body["rows"][0]["matched_rule"] == "Яндекс"


async def test_a_disabled_rule_never_matches(client: AsyncClient, categories):
    await _rule(
        client,
        name="Off",
        pattern="дивиденды",
        category_id=categories["Groceries"]["id"],
        is_enabled=False,
    )

    body = (
        await _preview(client, _workbook([[1, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге", 100, "KZT"]]))
    ).json()

    assert body["rows"][0]["category_id"] is None


async def test_conditions_narrow_a_rule(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="Only USD", pattern="дивиденды", category_id=groceries, currency="USD")

    body = (
        await _preview(
            client,
            _workbook(
                [
                    [1, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге", 100, "KZT"],
                    [2, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге", 100, "USD"],
                ]
            ),
        )
    ).json()

    assert body["rows"][0]["category_id"] is None
    assert body["rows"][1]["category_id"] == groceries


async def test_apply_is_a_dry_run_until_asked_otherwise(client: AsyncClient, categories, account_id):
    groceries = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, description="Яндекс Такси", date="2026-01-01"))
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=groceries)

    preview = (await client.post("/categorization-rules/apply", params={"dry_run": "true"})).json()
    assert preview["dry_run"] is True
    assert preview["matched"] == 1
    assert preview["written"] == 0
    assert preview["items"][0]["samples"] == ["Яндекс Такси"]
    assert (await client.get("/transactions")).json()["items"][0]["category_id"] is None

    applied = (await client.post("/categorization-rules/apply", params={"dry_run": "false"})).json()
    assert applied["written"] == 1
    assert (await client.get("/transactions")).json()["items"][0]["category_id"] == groceries


async def test_apply_leaves_already_categorized_rows_alone_by_default(
    client: AsyncClient, categories, account_id
):
    """A rule must never quietly overrule a category the user chose — that is
    what the explicit `only_uncategorized=false` is for."""
    dining = categories["Dining Out"]["id"]
    await client.post(
        "/transactions",
        json=_txn(account_id, description="Яндекс Такси", date="2026-01-01", category_id=dining),
    )
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=categories["Groceries"]["id"])

    result = (await client.post("/categorization-rules/apply", params={"dry_run": "false"})).json()

    assert result["considered"] == 0
    assert (await client.get("/transactions")).json()["items"][0]["category_id"] == dining


async def test_editing_a_rule_revalidates_its_pattern(client: AsyncClient, categories):
    rule = (await _rule(client, pattern="ok", category_id=categories["Groceries"]["id"])).json()

    bad = await client.patch(
        f"/categorization-rules/{rule['id']}", json={"pattern": "(broken", "match_type": "regex"}
    )
    assert bad.status_code == 422

    renamed = await client.patch(f"/categorization-rules/{rule['id']}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"


async def test_a_rule_fills_in_the_category_on_a_new_transaction(client: AsyncClient, categories, account_id):
    """The rule runs as a transaction is entered, not only in a batch."""
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=groceries)

    created = (
        await client.post("/transactions", json=_txn(account_id, description="Яндекс Такси"))
    ).json()

    assert created["category_id"] == groceries


async def test_an_explicit_category_is_never_overruled(client: AsyncClient, categories, account_id):
    dining = categories["Dining Out"]["id"]
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=categories["Groceries"]["id"])

    created = (
        await client.post(
            "/transactions",
            json=_txn(account_id, description="Яндекс Такси", category_id=dining),
        )
    ).json()

    assert created["category_id"] == dining


async def test_a_rule_pointing_at_the_wrong_kind_is_skipped(client: AsyncClient, categories, account_id):
    """A rule written for expenses must not label an income transaction with an
    expense category — that would misclassify it in every report. It is skipped
    rather than raising, because a 400 would block an entry the user wants."""
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=categories["Groceries"]["id"])

    created = (
        await client.post(
            "/transactions",
            json=_txn(account_id, type="income", description="Яндекс Такси"),
        )
    ).json()

    assert created["category_id"] is None


async def test_bulk_create_applies_rules_too(client: AsyncClient, categories, account_id):
    """The CSV import posts to /bulk, so it has to behave like the single create."""
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=groceries)

    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                _txn(account_id, description="Яндекс Такси"),
                _txn(account_id, description="Кофе"),
            ]
        },
    )
    assert resp.status_code == 201

    listed = (await client.get("/transactions")).json()["items"]
    by_description = {item["description"]: item for item in listed}
    assert by_description["Яндекс Такси"]["category_id"] == groceries
    assert by_description["Кофе"]["category_id"] is None


async def test_the_match_endpoint_reports_which_rule_would_decide(
    client: AsyncClient, categories, account_id
):
    """What the entry form shows the user while they type — the same answer the
    create path then acts on."""
    groceries = categories["Groceries"]["id"]
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=groceries)

    body = (
        await client.post(
            "/categorization-rules/match",
            json={
                "description": "Яндекс Такси",
                "amount": "10.00",
                "currency": "KZT",
                "account_id": account_id,
                "transaction_type": "expense",
            },
        )
    ).json()

    assert body["rule_name"] == "Яндекс"
    assert body["category_id"] == groceries
    assert body["category_name"] == "Groceries"


async def test_the_match_endpoint_says_nothing_when_no_rule_applies(
    client: AsyncClient, categories, account_id
):
    await _rule(client, name="Яндекс", pattern="яндекс", category_id=categories["Groceries"]["id"])

    body = (
        await client.post(
            "/categorization-rules/match",
            json={
                "description": "Кофе",
                "amount": "10.00",
                "currency": "KZT",
                "account_id": account_id,
                "transaction_type": "expense",
            },
        )
    ).json()

    assert body["rule_id"] is None
    assert body["category_id"] is None
