from datetime import date as date_
from decimal import Decimal
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.models.asset import Asset, AssetValuation
from app.models.enums import AssetValuationMode
from app.schemas.asset import (
    AssetCreate,
    AssetRead,
    AssetRevaluationAccept,
    AssetRevaluationReminderRead,
    AssetUpdate,
    AssetValuationCreate,
    AssetValuationRead,
)
from app.services.asset_depreciation_service import next_quarterly_revaluation_due, project_value
from app.services.exchange_rate_service import get_exchange_rate

router = APIRouter(prefix="/assets", tags=["assets"])
logger = logging.getLogger(__name__)

_EAGER = (selectinload(Asset.valuations),)


def _to_read(asset: Asset, projection_date: date_ | None = None) -> AssetRead:
    latest = asset.valuations[-1] if asset.valuations else None
    projection = None
    if asset.valuation_mode != AssetValuationMode.MANUAL_ONLY and asset.acquisition_date and asset.acquisition_cost is not None:
        try:
            projection = project_value(
                mode=asset.valuation_mode,
                acquisition_date=asset.acquisition_date,
                acquisition_cost=asset.acquisition_cost,
                residual_value=asset.residual_value,
                useful_life_years=asset.useful_life_years,
                annual_depreciation_rate=asset.annual_depreciation_rate,
                as_of_date=projection_date or date_.today(),
            )
        except ValueError:
            logger.warning("Invalid depreciation configuration for asset_id=%s", asset.id)
    return AssetRead(
        id=asset.id,
        name=asset.name,
        asset_class=asset.asset_class,
        currency=asset.currency,
        notes=asset.notes,
        capital_role=asset.capital_role,
        monthly_cash_flow=asset.monthly_cash_flow,
        risk_level=asset.risk_level,
        acquisition_date=asset.acquisition_date,
        acquisition_cost=asset.acquisition_cost,
        residual_value=asset.residual_value,
        valuation_mode=asset.valuation_mode,
        useful_life_years=asset.useful_life_years,
        annual_depreciation_rate=asset.annual_depreciation_rate,
        current_value=latest.value if latest else Decimal("0"),
        current_base_value_kzt=latest.base_value_kzt if latest else Decimal("0"),
        as_of_date=latest.as_of_date if latest else asset.created_at.date(),
        projected_value=projection.value if projection else None,
        accumulated_depreciation=projection.accumulated_depreciation if projection else None,
        latest_market_value=latest.value if latest else None,
        latest_market_value_date=latest.as_of_date if latest else None,
        unrealized_change=(latest.value - asset.acquisition_cost) if latest and asset.acquisition_cost is not None else None,
    )


@router.get("", response_model=list[AssetRead])
async def list_assets(as_of: date_ | None = None, session: AsyncSession = Depends(get_session)) -> list[AssetRead]:
    result = await session.execute(select(Asset).options(*_EAGER).order_by(Asset.name))
    return [_to_read(asset, as_of) for asset in result.scalars().all()]


@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(payload: AssetCreate, session: AsyncSession = Depends(get_session)) -> AssetRead:
    asset = Asset(
        name=payload.name,
        asset_class=payload.asset_class,
        currency=payload.currency,
        notes=payload.notes,
        capital_role=payload.capital_role,
        monthly_cash_flow=payload.monthly_cash_flow,
        risk_level=payload.risk_level,
        acquisition_date=payload.acquisition_date,
        acquisition_cost=payload.acquisition_cost,
        residual_value=payload.residual_value,
        valuation_mode=payload.valuation_mode,
        useful_life_years=payload.useful_life_years,
        annual_depreciation_rate=payload.annual_depreciation_rate,
    )
    session.add(asset)
    await session.flush()
    rate = payload.exchange_rate_to_kzt
    if rate is None:
        rate = (await get_exchange_rate(session, payload.as_of_date, payload.currency)).rate_to_kzt
    session.add(
        AssetValuation(
            asset_id=asset.id,
            value=payload.value,
            as_of_date=payload.as_of_date,
            exchange_rate_to_kzt=rate,
            base_value_kzt=payload.value * rate,
        )
    )
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset.id))
    return _to_read(refreshed.scalar_one())


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(asset_id: int, payload: AssetUpdate, session: AsyncSession = Depends(get_session)) -> AssetRead:
    result = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    updates = payload.model_dump(exclude_unset=True)
    try:
        AssetCreate.model_validate(
            {
                "name": updates.get("name", asset.name),
                "asset_class": updates.get("asset_class", asset.asset_class),
                "currency": updates.get("currency", asset.currency),
                "notes": updates.get("notes", asset.notes),
                "capital_role": updates.get("capital_role", asset.capital_role),
                "monthly_cash_flow": updates.get("monthly_cash_flow", asset.monthly_cash_flow),
                "risk_level": updates.get("risk_level", asset.risk_level),
                "acquisition_date": updates.get("acquisition_date", asset.acquisition_date),
                "acquisition_cost": updates.get("acquisition_cost", asset.acquisition_cost),
                "residual_value": updates.get("residual_value", asset.residual_value),
                "valuation_mode": updates.get("valuation_mode", asset.valuation_mode),
                "useful_life_years": updates.get("useful_life_years", asset.useful_life_years),
                "annual_depreciation_rate": updates.get("annual_depreciation_rate", asset.annual_depreciation_rate),
                "value": "0",
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_input=False, include_context=False),
        ) from exc
    for field, value in updates.items():
        setattr(asset, field, value)
    await session.commit()
    await session.refresh(asset, attribute_names=["valuations"])
    return _to_read(asset)


@router.post("/{asset_id}/valuations", response_model=AssetRead)
async def add_asset_valuation(
    asset_id: int, payload: AssetValuationCreate, session: AsyncSession = Depends(get_session)
) -> AssetRead:
    """Records (or corrects) an asset's value as of a date. Re-submitting the
    same date updates that day's value instead of erroring, so users can fix
    a typo without needing a separate edit flow."""
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    rate = payload.exchange_rate_to_kzt
    if rate is None:
        rate = (await get_exchange_rate(session, payload.as_of_date, asset.currency)).rate_to_kzt
    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(
            asset_id=asset_id,
            value=payload.value,
            as_of_date=payload.as_of_date,
            exchange_rate_to_kzt=rate,
            base_value_kzt=payload.value * rate,
        )
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={
                "value": payload.value,
                "exchange_rate_to_kzt": rate,
                "base_value_kzt": payload.value * rate,
            },
        )
    )
    await session.execute(upsert_stmt)
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    return _to_read(refreshed.scalar_one())


@router.get("/{asset_id}/valuations", response_model=list[AssetValuationRead])
async def list_asset_valuations(asset_id: int, session: AsyncSession = Depends(get_session)) -> list[AssetValuation]:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = await session.execute(
        select(AssetValuation).where(AssetValuation.asset_id == asset_id).order_by(AssetValuation.as_of_date)
    )
    return list(result.scalars().all())


@router.get("/revaluation-reminders", response_model=list[AssetRevaluationReminderRead])
async def list_revaluation_reminders(session: AsyncSession = Depends(get_session)) -> list[AssetRevaluationReminderRead]:
    result = await session.execute(select(Asset).options(*_EAGER).order_by(Asset.name))
    reminders = []
    for asset in result.scalars().all():
        latest = asset.valuations[-1] if asset.valuations else None
        if latest is None or asset.valuation_mode == AssetValuationMode.MANUAL_ONLY:
            continue
        due_date = next_quarterly_revaluation_due(latest.as_of_date)
        if due_date > date_.today():
            continue
        projection = _to_read(asset).projected_value
        if projection is not None:
            reminders.append(AssetRevaluationReminderRead(asset_id=asset.id, asset_name=asset.name, due_date=due_date, projected_value=projection, latest_market_value=latest.value, latest_market_value_date=latest.as_of_date))
    return sorted(reminders, key=lambda item: (item.due_date, item.asset_name.casefold()))


@router.post("/{asset_id}/revaluation-reminders/accept", response_model=AssetRead)
async def accept_projected_revaluation(
    asset_id: int,
    payload: AssetRevaluationAccept | None = None,
    session: AsyncSession = Depends(get_session),
) -> AssetRead:
    result = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.valuation_mode == AssetValuationMode.MANUAL_ONLY:
        raise HTTPException(status_code=409, detail="Manual-only assets have no depreciation projection")
    latest = asset.valuations[-1] if asset.valuations else None
    if latest is None:
        raise HTTPException(status_code=409, detail="No recorded valuation to update")
    as_of_date = payload.as_of_date if payload is not None else date_.today()
    read = _to_read(asset, as_of_date)
    if read.projected_value is None:
        raise HTTPException(status_code=409, detail="Asset has no valid depreciation projection")
    due = next_quarterly_revaluation_due(latest.as_of_date) <= as_of_date
    existing = next((item for item in asset.valuations if item.as_of_date == as_of_date), None)
    if not due and existing is not None and existing.value == read.projected_value:
        return _to_read(asset, as_of_date)
    if not due:
        raise HTTPException(status_code=409, detail="A quarterly revaluation is not due")
    rate = (await get_exchange_rate(session, as_of_date, asset.currency)).rate_to_kzt
    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(
            asset_id=asset.id,
            value=read.projected_value,
            as_of_date=as_of_date,
            exchange_rate_to_kzt=rate,
            base_value_kzt=read.projected_value * rate,
        )
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={
                "value": read.projected_value,
                "exchange_rate_to_kzt": rate,
                "base_value_kzt": read.projected_value * rate,
            },
        )
    )
    await session.execute(upsert_stmt)
    await session.commit()
    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset.id))
    return _to_read(refreshed.scalar_one())


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: int, session: AsyncSession = Depends(get_session)) -> None:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await session.delete(asset)
    await session.commit()
