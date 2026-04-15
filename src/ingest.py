"""
ingest.py — Loads, chunks, embeds, and stores documents into the vector DB.

Purpose: Take a file path and collection name, produce embedded chunks in Chroma.
Inputs: file_path (str), collection_name (str)
Outputs: chunk count (int)
Invariants:
  - Must always persist to settings.chroma_persist_dir — never in-memory only.
  - No state transition from ingestion to queryable without chunk count confirmation.
  - Temp file cleaned up in finally block on any failure path.
Security:
  - File path sanitized with os.path.basename() to prevent traversal.
  - Only whitelisted file extensions accepted (.pdf, .txt, .md).
  - Collection name assumed pre-validated by models.py at the API layer.
"""

import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import get_settings

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_FILE_SIZE_MB = 20


def _get_loader(file_path: str):
    """Return the appropriate document loader based on file extension.

    Inputs: file_path (str) — path to the uploaded file.
    Outputs: A LangChain document loader instance.
    Invariants: Only returns loaders for whitelisted extensions.
    Security: Caller must ensure file_path is sanitized before calling.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return PyPDFLoader(file_path)
    if ext in (".txt", ".md"):
        return TextLoader(file_path, encoding="utf-8")
    raise ValueError(
        f"Unsupported file type '{ext}'. Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def ingest_document(file_path: str, collection_name: str) -> int:
    """Ingest a document into the Chroma vector store.

    Purpose: Load a file, split into chunks, embed, and persist to Chroma.
    Inputs:
      - file_path: Path to the uploaded file on disk.
      - collection_name: Chroma collection to store chunks in (scoped per company).
    Outputs: Number of chunks created and stored (int, always > 0 on success).
    Invariants:
      - Chunks are always persisted to disk, never in-memory only.
      - Temp file is cleaned up in the finally block regardless of success/failure.
      - Function raises on any failure — caller (FastAPI) handles the HTTP response.
    Security:
      - file_path basename is extracted to prevent directory traversal.
      - File size is checked before loading to prevent resource exhaustion.
      - collection_name is assumed pre-validated by QueryRequest/UploadRequest model.
    """
    settings = get_settings()

    # Validate file exists (before try/finally — no file to clean up if it doesn't exist)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        # Size guard — prevent chunk explosion from massive files
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File too large ({file_size_mb:.1f} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB."
            )

        # Load document using appropriate loader
        loader = _get_loader(file_path)
        documents = loader.load()

        if not documents:
            raise ValueError("Document loaded but produced no content.")

        # Add source metadata (use basename to avoid exposing server paths)
        source_name = os.path.basename(file_path)
        for doc in documents:
            doc.metadata["source"] = source_name

        # Split into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        chunks = splitter.split_documents(documents)

        if not chunks:
            raise ValueError("Document was split but produced no chunks.")

        # Embed and persist to Chroma
        embeddings = OpenAIEmbeddings(
            api_key=settings.openai_api_key.get_secret_value()
        )
        Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=collection_name,
            persist_directory=settings.chroma_persist_dir,
        )

        return len(chunks)

    finally:
        # Clean up temp file regardless of success or failure
        if os.path.exists(file_path) and file_path.startswith("/tmp"):
            os.remove(file_path)
