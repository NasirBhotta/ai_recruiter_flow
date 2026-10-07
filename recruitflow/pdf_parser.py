"""
Local PDF text extraction and validation for RecruitFlow.
Identifies scanned, corrupted, or oversized files for routing to Needs Review.
"""

from __future__ import annotations

import io
from pathlib import Path
import re
from typing import NamedTuple
import logging
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

# Minimum character count to consider a document text-readable (vs purely scanned image)
MIN_READABLE_TEXT_LENGTH = 40


class PDFParseResult(NamedTuple):
    success: bool
    text: str
    error: str | None
    is_scanned: bool
    page_count: int
    file_size_bytes: int


def validate_pdf_bytes(
    file_bytes: bytes, max_size_mb: float = 10.0
) -> tuple[bool, str | None]:
    """Validate PDF file header and size limits."""
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > max_size_mb:
        return (
            False,
            f"File size ({size_mb:.2f} MB) exceeds configured limit of {max_size_mb:.1f} MB.",
        )

    # Validate PDF signature magic bytes: %PDF-
    if not file_bytes.startswith(b"%PDF-"):
        return False, "File is not a valid PDF document (missing %PDF header)."

    return True, None


def clean_extracted_text(text: str) -> str:
    """Normalize whitespace and strip unprintable characters."""
    # Remove null bytes and carriage returns
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple inline spaces
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_text_from_pdf(
    file_bytes: bytes, max_size_mb: float = 10.0
) -> PDFParseResult:
    """
    Extract readable text from PDF bytes.
    Routes corrupted, password-protected, or scanned image documents to error/scanned state.
    """
    file_size = len(file_bytes)

    # 1. Size & header check
    is_valid, validation_err = validate_pdf_bytes(file_bytes, max_size_mb)
    if not is_valid:
        return PDFParseResult(
            success=False,
            text="",
            error=validation_err,
            is_scanned=False,
            page_count=0,
            file_size_bytes=file_size,
        )

    # 2. Extract text using pypdf
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)

        if reader.is_encrypted:
            try:
                # Attempt empty password decrypt
                reader.decrypt("")
            except Exception:
                return PDFParseResult(
                    success=False,
                    text="",
                    error="PDF is password protected and cannot be read automatically.",
                    is_scanned=False,
                    page_count=page_count,
                    file_size_bytes=file_size,
                )

        extracted_pages: list[str] = []
        for idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    extracted_pages.append(page_text)
            except Exception as e:
                logger.warning(f"Error extracting text from page {idx + 1}: {e}")

        full_text = clean_extracted_text("\n\n".join(extracted_pages))

        # Check if text is virtually empty (indicative of scanned / flat image PDF)
        if len(full_text) < MIN_READABLE_TEXT_LENGTH:
            return PDFParseResult(
                success=False,
                text=full_text,
                error="PDF contains insufficient extractable text (likely a scanned image or empty document). Requires manual review.",
                is_scanned=True,
                page_count=page_count,
                file_size_bytes=file_size,
            )

        return PDFParseResult(
            success=True,
            text=full_text,
            error=None,
            is_scanned=False,
            page_count=page_count,
            file_size_bytes=file_size,
        )

    except PdfReadError as e:
        return PDFParseResult(
            success=False,
            text="",
            error=f"Corrupted or invalid PDF structure: {e}",
            is_scanned=False,
            page_count=0,
            file_size_bytes=file_size,
        )
    except Exception as e:
        return PDFParseResult(
            success=False,
            text="",
            error=f"Unexpected error while reading PDF: {e}",
            is_scanned=False,
            page_count=0,
            file_size_bytes=file_size,
        )


def extract_text_from_file(
    file_path: str | Path, max_size_mb: float = 10.0
) -> PDFParseResult:
    """Helper to extract text from a file path on disk."""
    path = Path(file_path)
    if not path.exists():
        return PDFParseResult(
            success=False,
            text="",
            error=f"File not found: {path}",
            is_scanned=False,
            page_count=0,
            file_size_bytes=0,
        )
    try:
        data = path.read_bytes()
        return extract_text_from_pdf(data, max_size_mb=max_size_mb)
    except Exception as e:
        return PDFParseResult(
            success=False,
            text="",
            error=f"Failed to read file: {e}",
            is_scanned=False,
            page_count=0,
            file_size_bytes=0,
        )
