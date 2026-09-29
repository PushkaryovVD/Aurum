"""Small, local-only helpers shared by PDF statement adapters."""
from io import BytesIO
import subprocess

from fastapi import HTTPException
from pypdf import PdfReader

from app.importers.ocr_worker import extract_pages


def extract_pdf_pages(content: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").replace("\xa0", " ") for page in reader.pages]
    except Exception as exc:
        raise HTTPException(422, "The PDF file could not be opened") from exc
    if not any(page.strip() for page in pages):
        raise HTTPException(422, "The PDF has no readable text layer; local OCR is required")
    return pages


def extract_pdf_pages_ocr(content: bytes) -> list[str]:
    """OCR inside the already isolated statement-preview worker process."""
    try:
        pages = extract_pages(content)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, "Local OCR timed out") from exc
    except Exception as exc:
        raise HTTPException(422, "Local OCR failed") from exc
    if not any(page.strip() for page in pages):
        raise HTTPException(422, "Local OCR did not recognise any text")
    return pages
