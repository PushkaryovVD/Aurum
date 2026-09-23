from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.importers import SUPPORTED_EXTENSIONS, resolve_importers
from app.schemas.statement_import import StatementCommit, StatementCommitResult, StatementPreview
from app.services.statement_import_service import commit_statement, suggest_row_categories

router = APIRouter(prefix="/statement-imports", tags=["statement-imports"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/preview", response_model=StatementPreview)
async def preview_statement(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_session)
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
    errors: list[str] = []
    for importer in importers:
        try:
            preview = importer.parse(name, content)
            break
        except HTTPException as exc:
            if exc.status_code != 422:
                raise
            errors.append(str(exc.detail))
    else:
        raise HTTPException(422, "Statement format was not recognized: " + "; ".join(errors))
    # Whatever the saved rules already decide is filled in here, so the user
    # reviews the real proposal instead of an empty category column.
    await suggest_row_categories(session, preview.rows)
    return preview


@router.post("/commit", response_model=StatementCommitResult)
async def save_statement(payload: StatementCommit, session: AsyncSession = Depends(get_session)):
    return await commit_statement(session, payload)
