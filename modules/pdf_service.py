"""Local extraction of selectable text from lecture PDF files."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from modules.ai_service import MAX_TRANSCRIPT_CHARACTERS

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100


class PDFExtractionError(Exception):
    """The PDF cannot be read as a supported text-based lecture document."""


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract selectable text from a bounded PDF, rejecting empty/scanned input."""
    if not pdf_bytes:
        raise PDFExtractionError("The PDF file is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise PDFExtractionError(
            f"The PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB. "
            "Please choose a smaller file."
        )

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise PDFExtractionError(
                "This PDF is password-protected. Upload an unlocked copy."
            )
        if len(reader.pages) > MAX_PDF_PAGES:
            raise PDFExtractionError(
                f"The PDF has more than {MAX_PDF_PAGES} pages. "
                "Split it into smaller sections and upload one at a time."
            )
        page_text = [page.extract_text() or "" for page in reader.pages]
    except PDFExtractionError:
        raise
    except (PdfReadError, FileNotDecryptedError, OSError, ValueError) as exc:
        raise PDFExtractionError(
            "The PDF could not be read. Check that it is a valid, unlocked PDF."
        ) from exc

    extracted_text = "\n\n".join(text.strip() for text in page_text if text.strip())
    if not extracted_text:
        raise PDFExtractionError(
            "No selectable text was found. This may be a scanned PDF; "
            "use a text-based PDF or run OCR on it first."
        )
    if len(extracted_text) > MAX_TRANSCRIPT_CHARACTERS:
        raise PDFExtractionError(
            f"The PDF contains more than {MAX_TRANSCRIPT_CHARACTERS:,} characters "
            "of text. Split it into smaller sections and upload one at a time."
        )
    return extracted_text
