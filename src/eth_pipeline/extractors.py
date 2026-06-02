"""
Pluggable content extractors for the eth-pipeline.

Provides the ``ContentExtractor`` protocol, a ``PdfExtractor`` implementation
(pypdfium2 primary / pypdf fallback), quality gates for empty or scanned
documents, and a simple format-based registry for future extractor types.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class ExtractorQualityError(Exception):
    """Raised when document quality prevents extraction (empty, scanned-only,
    corrupt)."""

    def __init__(self, message: str, reason: str = "quality_gate") -> None:
        self.reason = reason
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Result from a content extractor.

    Attributes
    ----------
    text:
        Full extracted text.
    page_count:
        Total number of pages in the source document.
    page_offsets:
        Cumulative character offset for the start of each page.
        Length = ``page_count + 1``, where ``offset[0] = 0`` and
        ``offset[page_count] = len(text)``.  For example ``[0, 523, 1047,
        1570]`` means page 0 is ``text[0:523]``, page 1 is ``text[523:1047]``,
        etc.
    metadata:
        Optional extractor-specific metadata (PDF version, title, etc.).
    """

    text: str
    page_count: int
    page_offsets: list[int]
    metadata: dict | None = None


# ---------------------------------------------------------------------------
# Extractor protocol
# ---------------------------------------------------------------------------


class ContentExtractor(Protocol):
    """Protocol for pluggable document content extractors.

    Implementations extract text with page-level offset tracking from a binary
    blob. The protocol is format-agnostic — implement for PDF, DOCX, images,
    etc.
    """

    def extract(self, content: bytes, filename: str = "") -> ExtractionResult:
        """Extract text from binary content.

        Parameters
        ----------
        content:
            Raw binary content of the document.
        filename:
            Original filename (may inform format detection).

        Returns
        -------
        ExtractionResult
            Full text + page offset metadata.

        Raises
        ------
        ExtractorQualityError
            Document is empty, scanned-only, or corrupt.
        """
        ...


# ---------------------------------------------------------------------------
# PdfExtractor — pypdfium2 (primary) / pypdf (fallback)
# ---------------------------------------------------------------------------


def _estimate_page_count(text: str, avg_chars_per_page: int = 3000) -> int:
    """Estimate page count from text length.

    Used by the pypdf fallback path which does not expose page-level
    information for scanned PDFs.

    Parameters
    ----------
    text:
        Extracted document text.
    avg_chars_per_page:
        Assumed average characters per page for estimation.

    Returns
    -------
    int
        Estimated page count (at least 1).
    """
    return max(1, (len(text) + avg_chars_per_page - 1) // avg_chars_per_page)


class PdfExtractor:
    """PDF text extractor using pypdfium2 (primary) or pypdf (fallback).

    Reads the ``USE_PYPDF`` environment variable to select the extraction
    backend.  When ``USE_PYPDF`` is truthy (``"true"``, ``"1"``, ``"yes"``),
    uses pypdf (Apache 2.0) as an AGPL-license mitigation path.  Otherwise
    uses pypdfium2 (BSD-3-Clause).

    All third-party imports are lazy — the module can be imported and used
    for type checks without the libraries being installed.  Actual extraction
    will fail at call time with ``ImportError`` if the required library is
    missing.

    Quality gate checks are applied after every extraction:

    * Empty text (after strip) raises ``ExtractorQualityError`` with
      ``reason="empty_or_scanned"``.
    * Zero-page PDFs raise ``ExtractorQualityError`` with ``reason="empty"``.
    * Very short text on multi-page PDFs raises
      ``ExtractorQualityError`` with ``reason="likely_scanned"``.
    """

    def extract(self, content: bytes, filename: str = "") -> ExtractionResult:
        """Extract text from a PDF binary blob.

        Parameters
        ----------
        content:
            Raw PDF bytes.
        filename:
            Original filename (used for logging / diagnostics).

        Returns
        -------
        ExtractionResult
            Extracted text with page-level offset tracking.

        Raises
        ------
        ExtractorQualityError
            Document is empty, scanned-only, or corrupt.
        """
        use_pypdf = os.environ.get("USE_PYPDF", "").strip().lower() in {"true", "1", "yes"}

        if use_pypdf:
            return self._extract_with_pypdf(content, filename)

        return self._extract_with_pypdfium2(content, filename)

    # ------------------------------------------------------------------
    # Primary: pypdfium2
    # ------------------------------------------------------------------

    def _extract_with_pypdfium2(self, content: bytes, filename: str) -> ExtractionResult:
        """Extract text using pypdfium2 (BSD-3-Clause)."""
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            logger.warning(
                "pypdfium2 not installed, falling back to pypdf: %s",
                exc,
            )
            return self._extract_with_pypdf(content, filename)

        try:
            pdf = pdfium.PdfDocument(content)
        except Exception as exc:
            raise ExtractorQualityError(
                f"Failed to open PDF with pypdfium2: {exc}",
                reason="corrupt",
            ) from exc

        if len(pdf) == 0:
            raise ExtractorQualityError(
                "The PDF has zero pages.",
                reason="empty",
            )

        page_texts: list[str] = []
        page_offsets: list[int] = [0]

        for i in range(len(pdf)):
            try:
                page = pdf[i]
                text_page = page.get_textpage()
                page_text = text_page.get_text_bounded()
                page_texts.append(page_text)
            except Exception as exc:
                logger.warning("Failed to extract text from page %d: %s", i, exc)
                page_texts.append("")
            offset = page_offsets[-1] + len(page_texts[-1])
            page_offsets.append(offset)

        # Account for \f separators inserted by "\f".join() below
        for i in range(2, len(page_offsets)):
            page_offsets[i] += i - 1

        text = "\f".join(page_texts)
        result = ExtractionResult(
            text=text,
            page_count=len(pdf),
            page_offsets=page_offsets,
        )

        self._apply_quality_gate(result)
        return result

    # ------------------------------------------------------------------
    # Fallback: pypdf
    # ------------------------------------------------------------------

    def _extract_with_pypdf(self, content: bytes, filename: str) -> ExtractionResult:
        """Extract text using pypdf (Apache-2.0, AGPL mitigation path).

        Note: pypdf's ``extract_text()`` is less accurate than pypdfium2's
        — this is the documented trade-off for the AGPL mitigation path.
        """
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "pypdf is required when USE_PYPDF=true: "
                "pip install eth-pipeline[pypdf]"
            ) from exc

        reader = PdfReader(io.BytesIO(content))

        if len(reader.pages) == 0:
            raise ExtractorQualityError(
                "The PDF has zero pages.",
                reason="empty",
            )

        page_texts: list[str] = []
        page_offsets: list[int] = [0]

        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("Failed to extract text from page %d via pypdf: %s", i, exc)
                page_text = ""
            page_texts.append(page_text)
            offset = page_offsets[-1] + len(page_text)
            page_offsets.append(offset)

        # Account for \f separators inserted by "\f".join() below
        for i in range(2, len(page_offsets)):
            page_offsets[i] += i - 1

        text = "\f".join(page_texts)
        result = ExtractionResult(
            text=text,
            page_count=len(reader.pages),
            page_offsets=page_offsets,
        )

        self._apply_quality_gate(result)
        return result

    # ------------------------------------------------------------------
    # Quality gate
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_quality_gate(result: ExtractionResult) -> None:
        """Validate extracted text quality.

        Raises ``ExtractorQualityError`` when the result fails quality
        checks (empty, scanned-only, or corrupt document).

        Parameters
        ----------
        result:
            Extraction result to validate.

        Raises
        ------
        ExtractorQualityError
            If quality checks fail.
        """
        text = result.text
        stripped = text.strip()

        if result.page_count == 0:
            raise ExtractorQualityError(
                "The PDF has zero pages.",
                reason="empty",
            )

        if not stripped:
            raise ExtractorQualityError(
                "The PDF appears to be empty or contains no extractable text "
                "(it may be a scanned document with no text layer). Try OCR or "
                "a document with embedded text.",
                reason="empty_or_scanned",
            )

        if len(stripped) < 50 and result.page_count > 1:
            raise ExtractorQualityError(
                f"The PDF has {result.page_count} pages but almost no "
                f"extractable text ({len(stripped)} chars). It may be a "
                f"scanned document. Try a document with a text layer or use "
                f"an OCR pipeline.",
                reason="likely_scanned",
            )


# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------

_extractors: dict[str, type[ContentExtractor]] = {}


def register_extractor(format: str, extractor_cls: type[ContentExtractor]) -> None:
    """Register a content extractor for a given format key.

    Parameters
    ----------
    format:
        Format identifier (e.g. ``"pdf"``, ``"docx"``).
    extractor_cls:
        Class implementing ``ContentExtractor`` protocol.
    """
    _extractors[format] = extractor_cls


def get_extractor(format: str) -> type[ContentExtractor] | None:
    """Look up a registered extractor by format key.

    Parameters
    ----------
    format:
        Format identifier (e.g. ``"pdf"``, ``"docx"``).

    Returns
    -------
    type[ContentExtractor] | None
        The registered extractor class, or ``None`` if not found.
    """
    return _extractors.get(format)


# Auto-register the PDF extractor
register_extractor("pdf", PdfExtractor)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def extract_text(content: bytes, filename: str = "") -> ExtractionResult:
    """Auto-detect format from filename and extract text.

    Uses the extension of *filename* to look up a registered extractor.
    Falls back to ``PdfExtractor`` when no extension is present or no
    extractor is registered.

    Parameters
    ----------
    content:
        Raw binary content of the document.
    filename:
        Original filename (used for format detection).

    Returns
    -------
    ExtractionResult
        Extracted text with page-level offset metadata.
    """
    ext = Path(filename).suffix.lower() if filename else ""
    format_map = {".pdf": "pdf"}
    fmt = format_map.get(ext, ext.lstrip(".") if ext else "pdf")
    cls = get_extractor(fmt) or PdfExtractor  # default to PDF
    return cls().extract(content, filename=filename)
