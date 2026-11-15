# main.py
"""
AnyFont → Nudi Converter – FastAPI application.

Endpoints
---------
GET  /api/health           – liveness probe
POST /api/convert/text     – convert a JSON text payload
POST /api/convert/file     – convert an uploaded file (multipart)

Run locally
-----------
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Any, Literal, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from converter import (
    auto_convert_to_nudi,
    auto_convert_to_unicode,
    convert_mixed_text,
    detect_encoding_type,
    nudi_to_unicode,
    process_file,
    unicode_to_nudi,
)

# ---------------------------------------------------------------------------
# Logging & Environment
# ---------------------------------------------------------------------------

ENVIRONMENT = os.getenv("ENVIRONMENT", "local").lower()
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*").strip()

if ALLOWED_ORIGINS_RAW == "*" or not ALLOWED_ORIGINS_RAW:
    allowed_origins = ["*"]
else:
    allowed_origins = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("anyfont_nudi")
logger.info("Starting AnyFont to Nudi Converter in '%s' environment on port %s", ENVIRONMENT, PORT)
logger.info("Configured CORS allowed origins: %s", allowed_origins)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AnyFont to Nudi Converter",
    description=(
        "Convert between legacy Nudi-encoded Kannada text and Unicode Kannada. "
        "Supports plain text, .docx, .pdf, and .xlsx files."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow configured origins and all Vercel deployment preview/production subdomains
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$" if allowed_origins != ["*"] else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

SourceEncoding = Literal["auto", "nudi", "unicode"]
TargetEncoding = Literal["nudi", "unicode"]


class TextConvertRequest(BaseModel):
    text: str = Field(..., description="The text to convert.")
    source_encoding: SourceEncoding = Field(
        "auto",
        description="Source encoding: 'auto' (detect), 'nudi', or 'unicode'.",
    )
    target_encoding: TargetEncoding = Field(
        "unicode",
        description="Target encoding: 'nudi' or 'unicode'.",
    )

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


class ConvertResponse(BaseModel):
    result: str
    source_type: str
    confidence: float
    segments: list[dict[str, Any]]


class FileConvertResponse(BaseModel):
    result: str
    source_type: str
    file_type: str
    metadata: dict[str, Any]
    segments: list[dict[str, Any]]
    confidence: float


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str = "local"


# ---------------------------------------------------------------------------
# Shared conversion helper
# ---------------------------------------------------------------------------

def _run_conversion(
    text: str,
    source_encoding: str,
    target_encoding: str,
) -> dict[str, Any]:
    """
    Core logic shared by text and file endpoints.

    Returns a dict with keys: result, source_type, confidence, segments.
    """
    detection = detect_encoding_type(text)
    effective_source = source_encoding if source_encoding != "auto" else detection["type"]
    confidence = detection["confidence"]

    if source_encoding == "auto":
        if target_encoding == "nudi":
            out = auto_convert_to_nudi(text)
        else:
            out = auto_convert_to_unicode(text)
        return {
            "result":      out["converted"],
            "source_type": out["source_type"],
            "confidence":  out["confidence"],
            "segments":    out["segments"],
        }

    # Explicit source specified
    if effective_source == target_encoding:
        # No conversion needed
        return {
            "result":      text,
            "source_type": effective_source,
            "confidence":  confidence,
            "segments":    [{"text": text, "type": effective_source, "converted": text}],
        }

    if effective_source == "mixed":
        out = convert_mixed_text(text, target=target_encoding)
        return {
            "result":      out["result"],
            "source_type": "mixed",
            "confidence":  confidence,
            "segments":    out["segments"],
        }

    if effective_source == "nudi" and target_encoding == "unicode":
        converted = nudi_to_unicode(text)
    elif effective_source == "unicode" and target_encoding == "nudi":
        converted = unicode_to_nudi(text)
    else:
        # latin or other – return as-is
        converted = text

    return {
        "result":      converted,
        "source_type": effective_source,
        "confidence":  confidence,
        "segments":    [{"text": text, "type": effective_source, "converted": converted}],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Utility"],
)
async def health_check() -> HealthResponse:
    """Return service liveness status and environment."""
    return HealthResponse(status="ok", version="1.0.0", environment=ENVIRONMENT)


@app.post(
    "/api/convert/text",
    response_model=ConvertResponse,
    summary="Convert a text string",
    tags=["Conversion"],
)
async def convert_text(request: TextConvertRequest) -> ConvertResponse:
    """
    Convert a Nudi-encoded or Unicode Kannada text string.

    - **source_encoding**: `auto` lets the service detect automatically.
    - **target_encoding**: `nudi` or `unicode`.
    """
    try:
        out = _run_conversion(request.text, request.source_encoding, request.target_encoding)
    except Exception as exc:
        logger.error("Text conversion error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {exc}",
        ) from exc

    return ConvertResponse(**out)


@app.post(
    "/api/convert/file",
    response_model=FileConvertResponse,
    summary="Convert an uploaded file",
    tags=["Conversion"],
)
async def convert_file(
    file: UploadFile = File(..., description="File to convert (.txt, .docx, .pdf, .xlsx)"),
    source_encoding: str = Form("auto", description="'auto', 'nudi', or 'unicode'"),
    target_encoding: str = Form("unicode", description="'nudi' or 'unicode'"),
) -> FileConvertResponse:
    """
    Upload a document and convert its Kannada text content.

    Supported file types: **txt**, **docx**, **pdf**, **xlsx**.
    """
    # Validate form values
    if source_encoding not in ("auto", "nudi", "unicode"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source_encoding must be 'auto', 'nudi', or 'unicode'; got {source_encoding!r}",
        )
    if target_encoding not in ("nudi", "unicode"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"target_encoding must be 'nudi' or 'unicode'; got {target_encoding!r}",
        )

    try:
        file_bytes   = await file.read()
        filename     = file.filename or "upload"
        content_type = file.content_type or "application/octet-stream"

        logger.info("Processing file: %s  (%d bytes, %s)", filename, len(file_bytes), content_type)

        parsed = process_file(file_bytes, filename, content_type)
        text      = parsed["text"]
        metadata  = parsed["metadata"]
        file_type = parsed["file_type"]

        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No text could be extracted from the uploaded file.",
            )

        out = _run_conversion(text, source_encoding, target_encoding)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("File conversion error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File processing failed: {exc}",
        ) from exc

    return FileConvertResponse(
        result=out["result"],
        source_type=out["source_type"],
        file_type=file_type,
        metadata=metadata,
        segments=out["segments"],
        confidence=out["confidence"],
    )


# ---------------------------------------------------------------------------
# Entry point (for direct `python main.py` runs)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=(ENVIRONMENT in ("local", "dev")))
