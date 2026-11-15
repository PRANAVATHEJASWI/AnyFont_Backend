# converter/document_processor.py
"""
File parsing utilities for the AnyFont → Nudi converter.

Supported file types
--------------------
* .txt  – plain text; tries multiple encodings
* .docx – Word document via python-docx
* .pdf  – PDF via PyMuPDF (fitz)
* .xlsx / .xls – Excel via openpyxl (read-only mode)

All processors return a normalised dict so the FastAPI layer has a uniform
interface regardless of file type.
"""

from __future__ import annotations

import io
import os
from typing import Any

try:
    import chardet
except ImportError:
    chardet = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# TXT processor
# ---------------------------------------------------------------------------

_TXT_ENCODINGS = ["windows-1252", "utf-8", "utf-8-sig", "latin-1", "iso-8859-1", "cp1252"]


def process_txt(file_bytes: bytes, filename: str = "file.txt") -> dict[str, Any]:
    """
    Decode a plain-text file, trying multiple encodings.

    Tries `windows-1252` first (most Nudi files are saved in this encoding),
    then `utf-8`, then chardet auto-detection, then falls back to `latin-1`
    which never raises a decode error.

    Returns
    -------
    dict:
        text         : str  – decoded text
        encoding_used: str  – the encoding that worked
        lines        : int  – number of lines
        size_bytes   : int  – raw byte count
    """
    # 1. Try ordered list of common encodings
    for enc in _TXT_ENCODINGS:
        try:
            text = file_bytes.decode(enc)
            return {
                "text":          text,
                "encoding_used": enc,
                "lines":         text.count("\n") + 1,
                "size_bytes":    len(file_bytes),
            }
        except (UnicodeDecodeError, LookupError):
            continue

    # 2. chardet auto-detection (if available)
    if chardet is not None:
        detected = chardet.detect(file_bytes)
        enc = detected.get("encoding") or "latin-1"
    else:
        enc = "latin-1"
    try:
        text = file_bytes.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        text = file_bytes.decode("latin-1", errors="replace")
        enc  = "latin-1 (fallback)"

    return {
        "text":          text,
        "encoding_used": enc,
        "lines":         text.count("\n") + 1,
        "size_bytes":    len(file_bytes),
    }


# ---------------------------------------------------------------------------
# DOCX processor
# ---------------------------------------------------------------------------

def process_docx(file_bytes: bytes) -> dict[str, Any]:
    """
    Extract text from a .docx file, preserving paragraph boundaries.

    Returns
    -------
    dict:
        text       : str – full text with paragraphs joined by newlines
        paragraphs : int – paragraph count
        size_bytes : int – raw byte count
    """
    try:
        from docx import Document  # python-docx
    except ImportError as exc:
        raise RuntimeError("python-docx is not installed") from exc

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs]
    text = "\n".join(paragraphs)

    return {
        "text":       text,
        "paragraphs": len(paragraphs),
        "size_bytes": len(file_bytes),
    }


# ---------------------------------------------------------------------------
# PDF processor
# ---------------------------------------------------------------------------

def process_pdf(file_bytes: bytes) -> dict[str, Any]:
    """
    Extract text from a PDF using PyMuPDF.

    Pages are separated by a form-feed character for downstream reference.

    Returns
    -------
    dict:
        text       : str – concatenated text of all pages
        pages      : int – page count
        size_bytes : int – raw byte count
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed") from exc

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_texts: list[str] = []
    for page in doc:
        page_texts.append(page.get_text("text"))

    doc.close()
    text = "\f".join(page_texts)   # form-feed between pages

    return {
        "text":       text,
        "pages":      len(page_texts),
        "size_bytes": len(file_bytes),
    }


# ---------------------------------------------------------------------------
# XLSX processor
# ---------------------------------------------------------------------------

def process_xlsx(file_bytes: bytes) -> dict[str, Any]:
    """
    Extract text from an Excel file (xlsx) using openpyxl.

    Cell values are joined with tabs; rows with newlines; sheets separated by
    a horizontal rule.

    Returns
    -------
    dict:
        text       : str – extracted text
        sheets     : int – sheet count
        rows       : int – total row count across all sheets
        size_bytes : int – raw byte count
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is not installed") from exc

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet_texts: list[str] = []
    total_rows = 0

    for ws in wb.worksheets:
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cell_values = [str(c) if c is not None else "" for c in row]
            rows.append("\t".join(cell_values))
        total_rows += len(rows)
        sheet_texts.append(f"[Sheet: {ws.title}]\n" + "\n".join(rows))

    wb.close()
    text = "\n\n".join(sheet_texts)

    return {
        "text":       text,
        "sheets":     len(sheet_texts),
        "rows":       total_rows,
        "size_bytes": len(file_bytes),
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_MIME_TO_EXT: dict[str, str] = {
    "text/plain":                                                        "txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword":                                                "docx",
    "application/pdf":                                                   "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel":                                          "xlsx",
}


def process_file(file_bytes: bytes, filename: str, content_type: str) -> dict[str, Any]:
    """
    Route to the appropriate processor based on file extension or MIME type.

    Returns
    -------
    dict:
        text      : str  – extracted text
        metadata  : dict – processor-specific metadata
        file_type : str  – 'txt' | 'docx' | 'pdf' | 'xlsx'
    """
    ext = os.path.splitext(filename)[-1].lstrip(".").lower()

    # Prefer extension; fall back to MIME sniffing
    if ext not in ("txt", "docx", "pdf", "xlsx", "xls"):
        ext = _MIME_TO_EXT.get(content_type, "txt")

    if ext == "txt":
        result = process_txt(file_bytes, filename)
        return {"text": result["text"], "metadata": result, "file_type": "txt"}

    if ext == "docx":
        result = process_docx(file_bytes)
        return {"text": result["text"], "metadata": result, "file_type": "docx"}

    if ext == "pdf":
        result = process_pdf(file_bytes)
        return {"text": result["text"], "metadata": result, "file_type": "pdf"}

    if ext in ("xlsx", "xls"):
        result = process_xlsx(file_bytes)
        return {"text": result["text"], "metadata": result, "file_type": "xlsx"}

    # Unknown type – treat as plain text
    result = process_txt(file_bytes, filename)
    return {"text": result["text"], "metadata": result, "file_type": "txt"}
