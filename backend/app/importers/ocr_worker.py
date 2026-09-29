"""Resource-bounded PDF rendering and OCR worker.

Run only as a subprocess through ``extract_pdf_pages_ocr``. Keeping PDFium and
Tesseract outside the web process means malformed documents cannot retain the
API worker's memory after the request is terminated.
"""
from io import BytesIO
import json
import resource
import shutil
import subprocess
import sys

OCR_DPI = 300
OCR_MAX_PAGES = 25
OCR_MAX_PAGE_PIXELS = 20_000_000
OCR_MAX_TOTAL_PIXELS = 120_000_000
OCR_PAGE_TIMEOUT_SECONDS = 20
OCR_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
OCR_CPU_LIMIT_SECONDS = 90


def validate_render_size(width: int, height: int) -> int:
    pixels = width * height
    if width <= 0 or height <= 0 or pixels > OCR_MAX_PAGE_PIXELS:
        raise ValueError("OCR page exceeds the pixel limit")
    return pixels


def extract_pages(content: bytes) -> list[str]:
    import pypdfium2 as pdfium

    binary = shutil.which("tesseract")
    if not binary:
        raise RuntimeError("Local OCR is not available")

    document = pdfium.PdfDocument(content)
    try:
        if len(document) > OCR_MAX_PAGES:
            raise ValueError(f"OCR statements are limited to {OCR_MAX_PAGES} pages")

        scale = OCR_DPI / 72
        total_pixels = 0
        dimensions: list[tuple[int, int]] = []
        for index in range(len(document)):
            page = document[index]
            width_points, height_points = page.get_size()
            width = round(width_points * scale)
            height = round(height_points * scale)
            total_pixels += validate_render_size(width, height)
            if total_pixels > OCR_MAX_TOTAL_PIXELS:
                raise ValueError("OCR statement exceeds the total pixel limit")
            dimensions.append((width, height))

        pages: list[str] = []
        for page_no, (width, height) in enumerate(dimensions, 1):
            bitmap = document[page_no - 1].render(scale=scale, grayscale=True)
            image = bitmap.to_pil()
            if image.size != (width, height):
                validate_render_size(*image.size)
            source = BytesIO()
            image.save(source, format="PNG")
            result = subprocess.run(
                [binary, "stdin", "stdout", "-l", "rus+eng", "--psm", "4"],
                input=source.getvalue(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=OCR_PAGE_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Local OCR failed on page {page_no}")
            pages.append(result.stdout.decode("utf-8", errors="replace").replace("\xa0", " "))
        return pages
    finally:
        document.close()


def main() -> int:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (OCR_MEMORY_LIMIT_BYTES, OCR_MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (OCR_CPU_LIMIT_SECONDS, OCR_CPU_LIMIT_SECONDS))
        pages = extract_pages(sys.stdin.buffer.read())
        sys.stdout.write(json.dumps(pages, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Only controlled messages are emitted; document text never goes to stderr.
        sys.stderr.write(str(exc)[:300])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
