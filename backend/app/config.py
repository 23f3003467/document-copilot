"""Single source of truth for backend environment configuration.

The settings object is created once at import time and is then used throughout
app startup and request processing. This fail-fast pattern prevents hidden
runtime bugs where a missing Supabase credential would only surface deep inside
another module.
"""

from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    database_runtime_url: str | None = None
    GEMINI_API_KEY: str
    GEMINI_EMBEDDING_MODEL: str
    GEMINI_EMBEDDING_DIMENSIONS: int
    GEMINI_CHAT_MODEL: str = "gemini-3.8-flash"
    BASE_URL: str
    # Comma-separated in .env; NoDecode skips JSON parsing so the validator sees the raw string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "CORS_ORIGINS")
    )

    @field_validator("supabase_url")
    @classmethod
    def require_https_supabase_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("SUPABASE_URL must be an https URL")
        return value

    @field_validator("database_url")
    @classmethod
    def require_direct_database_url(cls, value: str) -> str:
        # Alembic needs a session connection. The transaction pooler cannot run migrations.
        if "pooler.supabase.com" in value:
            raise ValueError(
                "DATABASE_URL must be the direct Supabase connection "
                "(db.<project-ref>.supabase.co), not the pooler"
            )
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return value

    @field_validator("database_runtime_url")
    @classmethod
    def require_postgres_runtime_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_RUNTIME_URL must be a PostgreSQL URL")

        parsed_url = urlsplit(value)
        if (
            parsed_url.hostname is not None
            and parsed_url.hostname.endswith(".pooler.supabase.com")
            and parsed_url.port != 5432
        ):
            raise ValueError(
                "DATABASE_RUNTIME_URL must use the Supabase session pooler "
                "on port 5432, not the transaction pooler"
            )
        return value

    @field_validator("GEMINI_EMBEDDING_DIMENSIONS")
    @classmethod
    def require_positive_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("GEMINI_EMBEDDING_DIMENSIONS must be a positive integer")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        else:
            origins = value
        if not origins:
            raise ValueError("ALLOWED_ORIGINS must list at least one origin")
        return origins

    @property
    def openai_api_key(self) -> str:
        return self.GEMINI_API_KEY

    @property
    def app_database_url(self) -> str:
        return self.database_runtime_url or self.database_url

    @property
    def openai_base_url(self) -> str:
        return self.BASE_URL

    @property
    def openai_chat_model(self) -> str:
        return self.GEMINI_CHAT_MODEL

    @property
    def openai_grounding_model(self) -> str:
        return self.GEMINI_CHAT_MODEL

    @property
    def openai_embedding_model(self) -> str:
        return self.GEMINI_EMBEDDING_MODEL

    @property
    def openai_embedding_dimensions(self) -> int:
        return self.GEMINI_EMBEDDING_DIMENSIONS

    @property
    def openai_agent_request_limit(self) -> int:
        return 8

    @property
    def retrieval_top_k(self) -> int:
        return 10

    @property
    def retrieval_candidate_k(self) -> int:
        return 50

    @property
    def retrieval_rrf_k(self) -> int:
        return 60

    @property
    def retrieval_neighbor_radius(self) -> int:
        return 1

    @property
    def retrieval_fts_config(self) -> str:
        return "english"

    @property
    def retrieval_fts_keyword_model(self) -> str:
        return self.GEMINI_CHAT_MODEL

    @property
    def retrieval_fts_keyword_min(self) -> int:
        return 3

    @property
    def retrieval_fts_keyword_max(self) -> int:
        return 5

    @property
    def retrieval_fts_keyword_fast_path_tokens(self) -> int:
        return 5


settings = Settings()
