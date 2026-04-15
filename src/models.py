"""
models.py — Pydantic request/response schemas enforcing the API contract.

Purpose: Define typed schemas for all API inputs and outputs.
Inputs: Raw dicts from FastAPI request parsing or retrieval layer.
Outputs: Validated, serialized JSON.
Invariants:
  - QueryResponse must always include answer, sources, AND confidence — never partial.
  - UploadResponse must always include chunk_count to confirm ingestion completed.
Security:
  - Models are internal validation only — no direct security surface.
  - company field is constrained to alphanumeric + hyphens + underscores to prevent
    collection name injection.
"""

import re

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The question to ask against the company's documents.",
    )
    company: str = Field(
        default="default",
        description="Company collection name. Alphanumeric, hyphens, underscores only.",
    )

    @field_validator("company")
    @classmethod
    def sanitize_company(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "company must contain only letters, numbers, hyphens, or underscores"
            )
        return v


class SourceDocument(BaseModel):
    content: str = Field(..., description="The relevant chunk text.")
    source: str = Field(..., description="Source document name or path.")
    page: int | None = Field(default=None, description="Page number if available.")


class QueryResponse(BaseModel):
    answer: str = Field(..., description="The grounded answer from retrieved documents.")
    sources: list[SourceDocument] = Field(
        ..., description="Source documents that informed the answer."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the retrieval."
    )
    declined: bool = Field(
        default=False,
        description="True if the confidence gate rejected the query.",
    )


class UploadResponse(BaseModel):
    message: str = Field(..., description="Status message.")
    collection: str = Field(..., description="The collection documents were stored in.")
    chunk_count: int = Field(
        ..., ge=0, description="Number of chunks created and stored."
    )


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    version: str = Field(default="1.0.0")
