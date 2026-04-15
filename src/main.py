"""
main.py — FastAPI app exposing /upload, /query, and /health endpoints.

Purpose: HTTP layer wiring config, models, ingest, and retrieval modules together.
Inputs: HTTP requests.
Outputs: JSON responses typed by Pydantic models.
Invariants:
  - All blocking I/O must be wrapped in run_in_threadpool.
  - CORS must be configured for frontend access.
  - All responses use Pydantic response_model — never a raw dict.
  - company param sanitized at the model layer (QueryRequest/UploadResponse).
Security:
  - Unvalidated company param could access other collections — sanitized by models.py.
  - File type validated before ingestion.
  - No raw tracebacks exposed — structured JSON errors only.
  - /health must not expose API keys or file paths.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import get_settings
from src.ingest import ingest_document
from src.models import HealthResponse, QueryRequest, QueryResponse, UploadResponse
from src.retrieval import query_brain

# Validate config on startup — fail fast if OPENAI_API_KEY is missing
get_settings()

app = FastAPI(
    title="Company Brain",
    description="Internal knowledge base powered by RAG",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_company(company: str) -> str:
    """Validate and sanitize the company parameter.

    Reuses the same regex as QueryRequest.company validator.
    Needed here because /upload receives company as a form field,
    not through the QueryRequest model.
    """
    company = company.strip()
    if not company:
        return "default"
    if not re.match(r"^[a-zA-Z0-9_-]+$", company):
        raise HTTPException(
            status_code=422,
            detail="company must contain only letters, numbers, hyphens, or underscores",
        )
    return company


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint. Returns status only — no secrets or paths."""
    return HealthResponse()


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    company: str = Form(default="default"),
):
    """Upload and ingest a document into the company's knowledge base.

    Inputs: Multipart file upload + company form field.
    Outputs: UploadResponse with chunk count.
    Security: File type checked, company param sanitized, temp file cleaned by ingest.
    """
    company = _sanitize_company(company)

    # Validate file type before writing to disk
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf", ".txt", ".md"}:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Supported: .pdf, .txt, .md",
        )

    # Write uploaded file to a temp location
    suffix = ext
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/tmp")
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()

        # Run blocking ingest in threadpool
        chunk_count = await run_in_threadpool(
            ingest_document, tmp.name, company
        )

        return UploadResponse(
            message="Document ingested successfully.",
            collection=company,
            chunk_count=chunk_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {str(e)}")


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Query the company's knowledge base.

    Inputs: QueryRequest with question and company.
    Outputs: QueryResponse with answer, sources, confidence, declined.
    Security: company pre-validated by QueryRequest model, question length capped.
    """
    try:
        result = await run_in_threadpool(
            query_brain, request.question, request.company
        )

        return QueryResponse(**result)
    except Exception as e:
        error_msg = str(e)
        if "does not exist" in error_msg.lower() or "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{request.company}' not found. Upload documents first.",
            )
        raise HTTPException(status_code=503, detail=f"Query failed: {error_msg}")


# Serve frontend — must be after API routes so /health, /upload, /query take priority
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the frontend single-page app."""
    return FileResponse(FRONTEND_DIR / "index.html")
