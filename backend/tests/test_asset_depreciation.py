from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.models.asset import AssetValuation


async def _create_asset(client: AsyncClient, **overrides) -> dict:
    payload = {
        "name": "Test vehicle",
        "asset_class": "vehicles",
        "currency": "KZT",
        "value": "1200000.00",
        "as_of_date": "2024-02-29",
        "exchange_rate_to_kzt": "1",
        "acquisition_date": "2024-02-29",
        "acquisition_cost": "1200000.00",
        "residual_value": "200000.00",
        "valuation_mode": "straight_line",
        "useful_life_years": 4,
    }
    payload.update(overrides)
    response = await client.post("/assets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_as_of_projection_do_not_mutate_recorded_snapshot(client: AsyncClient):
    asset = await _create_asset(client)
    assert asset["latest_market_value"] == "1200000.00"
    assert asset["latest_market_value_date"] == "2024-02-29"
    assert asset["unrealized_change"] == "0.00"

    projected = (await client.get("/assets", params={"as_of": "2026-02-28"})).json()[0]
    assert projected["projected_value"] == "700000.00"
    assert projected["accumulated_depreciation"] == "500000.00"
    assert projected["current_value"] == "1200000.00"

    valuations = (await client.get(f"/assets/{asset['id']}/valuations")).json()
    assert len(valuations) == 1
    assert valuations[0]["value"] == "1200000.00"


async def test_manual_only_asset_needs_no_depreciation_inputs(client: AsyncClient):
    asset = await _create_asset(
        client,
        name="Painting",
        asset_class="other",
        acquisition_date=None,
        acquisition_cost=None,
        residual_value=None,
        valuation_mode="manual_only",
        useful_life_years=None,
    )
    assert asset["valuation_mode"] == "manual_only"
    assert asset["projected_value"] is None
    assert asset["accumulated_depreciation"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"residual_value": "1200000.01"},
        {"acquisition_date": None},
        {"acquisition_cost": None},
        {"useful_life_years": None},
        {"useful_life_years": 0},
        {"useful_life_years": 101},
        {"acquisition_cost": "-1"},
        {"valuation_mode": "annual_percentage", "useful_life_years": None, "annual_depreciation_rate": None},
        {"valuation_mode": "annual_percentage", "useful_life_years": None, "annual_depreciation_rate": "0"},
        {"valuation_mode": "annual_percentage", "useful_life_years": None, "annual_depreciation_rate": "100"},
    ],
)
async def test_create_rejects_invalid_depreciation_configuration(client: AsyncClient, overrides):
    payload = {
        "name": "Invalid",
        "asset_class": "vehicles",
        "currency": "KZT",
        "value": "1000.00",
        "acquisition_date": "2024-01-01",
        "acquisition_cost": "1000.00",
        "residual_value": "0",
        "valuation_mode": "straight_line",
        "useful_life_years": 5,
    }
    payload.update(overrides)
    response = await client.post("/assets", json=payload)
    assert response.status_code == 422


async def test_patch_validates_final_state_and_preserves_valuations(client: AsyncClient):
    asset = await _create_asset(client, valuation_mode="manual_only", useful_life_years=None)
    before = (await client.get(f"/assets/{asset['id']}/valuations")).json()

    invalid = await client.patch(f"/assets/{asset['id']}", json={"valuation_mode": "straight_line"})
    assert invalid.status_code == 422

    valid = await client.patch(
        f"/assets/{asset['id']}",
        json={"valuation_mode": "straight_line", "useful_life_years": 8},
    )
    assert valid.status_code == 200, valid.text
    assert (await client.get(f"/assets/{asset['id']}/valuations")).json() == before


async def test_overdue_reminder_accept_is_idempotent(client: AsyncClient, test_sessionmaker):
    old_date = date.today() - timedelta(days=130)
    asset = await _create_asset(client, as_of_date=old_date.isoformat(), acquisition_date="2020-01-01")

    reminders = (await client.get("/assets/revaluation-reminders")).json()
    assert [item["asset_id"] for item in reminders] == [asset["id"]]
    assert reminders[0]["latest_market_value"] == "1200000.00"

    first = await client.post(f"/assets/{asset['id']}/revaluation-reminders/accept")
    second = await client.post(f"/assets/{asset['id']}/revaluation-reminders/accept")
    assert first.status_code == second.status_code == 200
    assert (await client.get("/assets/revaluation-reminders")).json() == []

    async with test_sessionmaker() as session:
        count = await session.scalar(
            select(func.count()).select_from(AssetValuation).where(
                AssetValuation.asset_id == asset["id"], AssetValuation.as_of_date == date.today()
            )
        )
    assert count == 1


async def test_reminder_accept_conflict_cases(client: AsyncClient, test_sessionmaker):
    manual = await _create_asset(client, name="Manual", valuation_mode="manual_only", useful_life_years=None)
    assert (await client.post(f"/assets/{manual['id']}/revaluation-reminders/accept")).status_code == 409

    current = await _create_asset(client, name="Current", as_of_date=date.today().isoformat())
    assert (await client.post(f"/assets/{current['id']}/revaluation-reminders/accept")).status_code == 409

    no_snapshot = await _create_asset(client, name="No snapshot")
    async with test_sessionmaker() as session:
        await session.execute(delete(AssetValuation).where(AssetValuation.asset_id == no_snapshot["id"]))
        await session.commit()
    assert (await client.post(f"/assets/{no_snapshot['id']}/revaluation-reminders/accept")).status_code == 409
    assert (await client.post("/assets/999999/revaluation-reminders/accept")).status_code == 404


async def test_manual_market_revaluation_clears_reminder(client: AsyncClient):
    asset = await _create_asset(client, as_of_date=(date.today() - timedelta(days=130)).isoformat())
    assert (await client.get("/assets/revaluation-reminders")).json()
    recorded = await client.post(
        f"/assets/{asset['id']}/valuations",
        json={"value": "910000.00", "as_of_date": date.today().isoformat(), "exchange_rate_to_kzt": "1"},
    )
    assert recorded.status_code == 200
    assert (await client.get("/assets/revaluation-reminders")).json() == []


async def test_depreciation_configuration_does_not_change_net_worth_until_accepted(client: AsyncClient):
    asset = await _create_asset(client, exchange_rate_to_kzt="1")
    before = (await client.get("/net-worth/summary", params={"range": "all"})).json()
    updated = await client.patch(
        f"/assets/{asset['id']}",
        json={"useful_life_years": 8, "acquisition_cost": "1100000.00"},
    )
    assert updated.status_code == 200
    after = (await client.get("/net-worth/summary", params={"range": "all"})).json()
    assert after["current"] == before["current"]
    assert after["change_amount"] == before["change_amount"]
    assert after["breakdown"] == before["breakdown"]
