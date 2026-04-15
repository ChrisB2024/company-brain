"""
config.py — Single source of truth for all environment-driven configuration.

Purpose: Load and validate all settings from .env via pydantic-settings.
Inputs: Environment variables (or .env file).
Outputs: Settings singleton via get_settings().
Invariants:
  - openai_api_key must always be present — app fails fast on startup if missing.
  - All config values have sensible defaults except the API key.
Security:
  - .env must never be committed (.gitignore enforced).
  - API key is typed as SecretStr — never serialized to logs or responses.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Required — no default, app fails fast if missing
    openai_api_key: SecretStr

    # Vector store
    chroma_persist_dir: str = "./chroma_db"

    # LLM
    model_name: str = "gpt-4o"
    temperature: float = 0.0

    # Chunking
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Retrieval
    retrieval_k: int = 4
    confidence_threshold: float = 0.75


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Raises ValidationError on startup if
    required env vars (e.g. OPENAI_API_KEY) are missing."""
    return Settings()
