from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.envelope import EnvelopeAuditLog, EnvelopeMonth, EnvelopeTemplate, EnvelopeTemplateItem
from app.schemas.envelope import (
    EnvelopeAllocationInput,
    EnvelopeAuditRead,
    EnvelopeFundInput,
    EnvelopeFundResult,
    EnvelopeMonthSummary,
    EnvelopeMoveInput,
    EnvelopeStatus,
    EnvelopeTemplateInput,
    EnvelopeTemplateItemRead,
    EnvelopeTemplateRead,
)
from app.services.envelope_service import (
    apply_template,
    close_month,
    delete_allocation,
    fund,
    fund_next_month as fund_next_envelope_month,
    get_status,
    move,
    open_month,
    reopen_month,
    set_allocation,
    _expense_category,
)

router = APIRouter(prefix="/envelopes", tags=["envelopes"])
YEAR = Path(ge=2000, le=2100)
MONTH = Path(ge=1, le=12)


async def _template_read(session: AsyncSession, template: EnvelopeTemplate) -> EnvelopeTemplateRead:
    items = list(
        (
            await session.execute(
                select(EnvelopeTemplateItem)
                .where(EnvelopeTemplateItem.template_id == template.id)
                .order_by(EnvelopeTemplateItem.id)
            )
        ).scalars()
    )
    return EnvelopeTemplateRead(
        id=template.id,
        name=template.name,
        items=[EnvelopeTemplateItemRead.model_validate(item, from_attributes=True) for item in items],
    )


@router.get("/templates", response_model=list[EnvelopeTemplateRead])
async def list_templates(session: AsyncSession = Depends(get_session)) -> list[EnvelopeTemplateRead]:
    templates = list((await session.execute(select(EnvelopeTemplate).order_by(EnvelopeTemplate.name, EnvelopeTemplate.id))).scalars())
    return [await _template_read(session, template) for template in templates]


async def _replace_template_items(session: AsyncSession, template: EnvelopeTemplate, payload: EnvelopeTemplateInput) -> None:
    for item in payload.items:
        await _expense_category(session, item.category_id)
    template.name = payload.name
    await session.execute(delete(EnvelopeTemplateItem).where(EnvelopeTemplateItem.template_id == template.id))
    session.add_all(EnvelopeTemplateItem(template_id=template.id, **item.model_dump()) for item in payload.items)


@router.post("/templates", response_model=EnvelopeTemplateRead, status_code=201)
async def create_template(payload: EnvelopeTemplateInput, session: AsyncSession = Depends(get_session)) -> EnvelopeTemplateRead:
    template = EnvelopeTemplate(name=payload.name)
    session.add(template)
    await session.flush()
    await _replace_template_items(session, template, payload)
    await session.commit()
    return await _template_read(session, template)


@router.patch("/templates/{template_id}", response_model=EnvelopeTemplateRead)
async def update_template(template_id: int, payload: EnvelopeTemplateInput, session: AsyncSession = Depends(get_session)) -> EnvelopeTemplateRead:
    template = await session.get(EnvelopeTemplate, template_id)
    if template is None:
        raise HTTPException(404, "Envelope template not found")
    await _replace_template_items(session, template, payload)
    await session.commit()
    return await _template_read(session, template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    template = await session.get(EnvelopeTemplate, template_id)
    if template is None:
        raise HTTPException(404, "Envelope template not found")
    await session.delete(template)
    await session.commit()
    return Response(status_code=204)


@router.get("", response_model=list[EnvelopeMonthSummary])
async def list_months(session: AsyncSession = Depends(get_session)) -> list[EnvelopeMonthSummary]:
    rows = list((await session.execute(select(EnvelopeMonth).order_by(EnvelopeMonth.year.desc(), EnvelopeMonth.month.desc()))).scalars())
    result = []
    for row in rows:
        status = await get_status(session, row.year, row.month)
        result.append(EnvelopeMonthSummary(year=row.year, month=row.month, is_closed=row.is_closed, has_ledger_drift=status.has_ledger_drift))
    return result


@router.get("/{year}/{month}", response_model=EnvelopeStatus)
async def status(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await get_status(session, year, month)


@router.post("/{year}/{month}/open", response_model=EnvelopeStatus)
async def open_envelope_month(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await open_month(session, year, month)


@router.put("/{year}/{month}/allocations/{category_id}", response_model=EnvelopeStatus)
async def allocation(category_id: int, payload: EnvelopeAllocationInput, year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await set_allocation(session, year, month, category_id, payload)


@router.delete("/{year}/{month}/allocations/{category_id}", response_model=EnvelopeStatus)
async def remove_allocation(category_id: int, year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await delete_allocation(session, year, month, category_id)


@router.post("/{year}/{month}/moves", response_model=EnvelopeStatus, status_code=201)
async def envelope_move(payload: EnvelopeMoveInput, year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await move(session, year, month, payload)


@router.post("/{year}/{month}/apply-template/{template_id}", response_model=EnvelopeStatus)
async def apply_envelope_template(template_id: int, year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await apply_template(session, year, month, template_id)


@router.post("/{year}/{month}/fund", response_model=EnvelopeFundResult)
async def fund_envelopes(payload: EnvelopeFundInput, year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeFundResult:
    return await fund(session, year, month, payload)


@router.post("/{year}/{month}/fund-next-month", response_model=EnvelopeFundResult)
async def fund_next_month(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeFundResult:
    return await fund_next_envelope_month(session, year, month)


@router.post("/{year}/{month}/close", response_model=EnvelopeStatus)
async def close_envelope_month(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await close_month(session, year, month)


@router.post("/{year}/{month}/reopen", response_model=EnvelopeStatus)
async def reopen_envelope_month(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> EnvelopeStatus:
    return await reopen_month(session, year, month)


@router.get("/{year}/{month}/audit", response_model=list[EnvelopeAuditRead])
async def audit(year: int = YEAR, month: int = MONTH, session: AsyncSession = Depends(get_session)) -> list[EnvelopeAuditLog]:
    return list((await session.execute(select(EnvelopeAuditLog).where(EnvelopeAuditLog.year == year, EnvelopeAuditLog.month == month).order_by(EnvelopeAuditLog.id))).scalars())
