import asyncio
import json
import os
from pathlib import Path
import signal
import sys

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.importers import SUPPORTED_EXTENSIONS, resolve_importers
from app.schemas.statement_import import StatementCommit, StatementCommitResult, StatementPreview
from app.services.statement_import_service import commit_statement, suggest_row_categories

router = APIRouter(prefix="/statement-imports", tags=["statement-imports"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PREVIEW_TIMEOUT_SECONDS = 130
_preview_slot = asyncio.Semaphore(1)
_WORKER_PATH = Path(__file__).resolve().parents[2] / "importers" / "statement_preview_worker.py"


async def _kill_and_reap(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        await process.wait()


async def _parse_in_worker(name: str, content: bytes) -> StatementPreview:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_WORKER_PATH),
        name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(content),
            timeout=PREVIEW_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        await _kill_and_reap(process)
        raise HTTPException(422, "Statement parsing timed out") from exc
    except BaseException:
        if process.returncode is None:
            await _kill_and_reap(process)
        raise

    if process.returncode != 0:
        raise HTTPException(422, "Statement parsing failed")
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Statement parser returned an invalid result") from exc
    if not isinstance(result, dict):
        raise HTTPException(422, "Statement parser returned an invalid result")
    if error := result.get("error"):
        raise HTTPException(422, str(error))
    try:
        return StatementPreview.model_validate(result["preview"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, "Statement parser returned an invalid result") from exc


@router.post("/preview", response_model=StatementPreview)
async def preview_statement(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> StatementPreview:
    """Reads a bank document and returns what it recognised — without writing
    anything. The user reviews and corrects these rows, then posts them back to
    /commit; nothing reaches the ledger until they do."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Statement file is larger than 10 MB")
    name = file.filename or "statement"
    importers = resolve_importers(name)
    if not importers:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise HTTPException(422, f"Unsupported file type. Supported formats: {supported}")
    async with _preview_slot:
        preview = await _parse_in_worker(name, content)
    # Whatever the saved rules already decide is filled in here, so the user
    # reviews the real proposal instead of an empty category column.
    await suggest_row_categories(session, preview.rows, context=context)
    return preview


@router.post("/commit", response_model=StatementCommitResult)
async def save_statement(
    payload: StatementCommit,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
):
    return await commit_statement(session, payload, context)
