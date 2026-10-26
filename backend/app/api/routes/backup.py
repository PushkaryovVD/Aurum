from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_app_settings, get_request_workspace, get_session
from app.core.audit import log_destructive
from app.core.config import Settings
from app.models.workspace import WorkspaceRole
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])


def require_legacy_backup_mode(settings: Settings = Depends(get_app_settings)) -> None:
    """Keep the installation-wide backup API out of workspace-aware mode.

    The existing format has no workspace, authorization, or collision semantics.
    Serving it after application authentication is enabled would either disclose
    every workspace or let one member replace the entire installation.
    """
    if settings.app_auth_required:
        raise HTTPException(status_code=503, detail="Workspace backup unavailable")


@router.get("/export", response_model=BackupPayload)
async def export_backup(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> BackupPayload:
    """Legacy mode exports the installation; with accounts it exports only
    the active workspace, and only to its owner."""
    if not settings.app_auth_required:
        return await build_backup(session)
    if context.membership is None or context.membership.role != WorkspaceRole.OWNER:
        raise HTTPException(status_code=403, detail="Only the workspace owner can export it")
    return await build_backup(session, workspace_id=context.workspace_id)


@router.post("/import", dependencies=[Depends(require_legacy_backup_mode)])
async def import_backup(payload: BackupPayload, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    # Logged before the fact as well as after: if the restore dies partway
    # (it rolls back, but the process could also be killed outright), the
    # "started" line is the only evidence it was ever attempted.
    log_destructive(
        "backup.restore.started",
        exported_at=payload.exported_at,
        source_app_version=payload.app_version,
        accounts=len(payload.accounts),
        transactions=len(payload.transactions),
    )
    await restore_backup(session, payload)
    log_destructive("backup.restore.completed", transactions=len(payload.transactions))
    return {"status": "ok"}
