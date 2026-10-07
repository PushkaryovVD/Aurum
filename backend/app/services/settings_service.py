from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace
from app.models.settings import AppSettings


async def get_or_create_app_settings(session: AsyncSession, context: RequestWorkspace) -> AppSettings:
    """Return the request namespace's settings, creating it safely if absent.

    ``None`` is exclusively the legacy auth-disabled namespace and retains
    id=1 semantics. Authenticated callers always query by their workspace ID,
    so they can neither observe nor mutate the preserved legacy row.
    """
    if context.workspace_id is None:
        settings = await session.get(AppSettings, 1)
        if settings is not None:
            return settings
        settings = AppSettings(id=1)
    else:
        settings = (
            await session.execute(
                select(AppSettings).where(AppSettings.workspace_id == context.workspace_id)
            )
        ).scalar_one_or_none()
        if settings is not None:
            return settings
        settings = AppSettings(workspace_id=context.workspace_id)

    try:
        async with session.begin_nested():
            session.add(settings)
            await session.flush()
    except IntegrityError:
        # A concurrent creator won the partial unique index race. The savepoint
        # leaves the caller's transaction usable; re-read its committed row.
        if context.workspace_id is None:
            settings = await session.get(AppSettings, 1)
        else:
            settings = (
                await session.execute(
                    select(AppSettings).where(AppSettings.workspace_id == context.workspace_id)
                )
            ).scalar_one()
        return settings

    await session.commit()
    await session.refresh(settings)
    return settings
