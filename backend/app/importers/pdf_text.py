"""Small, local-only helpers shared by text-layer PDF statement adapters."""
from io import BytesIO

from fastapi import HTTPException
from pypdf import PdfReader


def extract_pdf_pages(content: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").replace("\xa0", " ") for page in reader.pages]
    except Exception as exc:
        raise HTTPException(422, "The PDF file could not be opened") from exc
    if not any(page.strip() for page in pages):
        raise HTTPException(422, "The PDF has no readable text layer; local OCR is required")
    return pages
