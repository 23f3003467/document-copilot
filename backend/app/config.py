"""Single source of truth for backend environment configuration."""

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    GEMINI_API_KEY: str
    GEMINI_EMBEDDING_MODEL: str
    GEMINI_EMBEDDING_DIMENSIONS: int
    BASE_URL: str
    # Comma-separated in .env; NoDecode skips JSON parsing so the validator sees the raw string.
    cors_origins: Annotated[list[str], NoDecode]

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


settings = Settings()
