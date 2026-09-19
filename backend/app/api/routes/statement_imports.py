from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.importers import SUPPORTED_EXTENSIONS, resolve_importer
from app.schemas.statement_import import StatementCommit, StatementCommitResult, StatementPreview
from app.services.statement_import_service import commit_statement

router = APIRouter(prefix="/statement-imports", tags=["statement-imports"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/preview", response_model=StatementPreview)
async def preview_statement(file: UploadFile = File(...)) -> StatementPreview:
    """Reads a bank document and returns what it recognised — without writing
    anything. The user reviews and corrects these rows, then posts them back to
    /commit; nothing reaches the ledger until they do."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Statement file is larger than 10 MB")
    name = file.filename or "statement"
    importer = resolve_importer(name)
    if importer is None:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise HTTPException(422, f"Unsupported file type. Supported formats: {supported}")
    return importer.parse(name, content)


@router.post("/commit", response_model=StatementCommitResult)
async def save_statement(payload: StatementCommit, session: AsyncSession = Depends(get_session)):
    return await commit_statement(session, payload)
