import pytest
from pydantic import ValidationError

from app.config import _BACKEND_ENV_FILE, Settings


def test_env_file_path_is_independent_of_working_directory() -> None:
    assert _BACKEND_ENV_FILE.is_absolute()
    assert _BACKEND_ENV_FILE.name == ".env"
    assert _BACKEND_ENV_FILE.parent.name == "backend"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "anon",
        "supabase_service_role_key": "service-role",
        "database_url": "postgresql://postgres:password@db.example.supabase.co/postgres",
        "GEMINI_API_KEY": "test-key",
        "GEMINI_EMBEDDING_MODEL": "embedding-model",
        "GEMINI_EMBEDDING_DIMENSIONS": 768,
        "BASE_URL": "https://example.com/v1",
        "cors_origins": ["http://localhost:5173"],
    }
    values.update(overrides)
    return Settings(**values)


def test_runtime_database_url_defaults_to_direct_connection() -> None:
    settings = _settings(database_runtime_url=None)

    assert settings.app_database_url == settings.database_url


def test_runtime_database_url_accepts_session_pooler() -> None:
    runtime_url = (
        "postgresql://postgres.project-ref:password@"
        "aws-0-region.pooler.supabase.com:5432/postgres"
    )

    settings = _settings(database_runtime_url=runtime_url)

    assert settings.app_database_url == runtime_url
    assert settings.database_url.endswith("@db.example.supabase.co/postgres")


def test_runtime_database_url_rejects_transaction_pooler() -> None:
    with pytest.raises(ValidationError, match="session pooler"):
        _settings(
            database_runtime_url=(
                "postgresql://postgres.project-ref:password@"
                "aws-0-region.pooler.supabase.com:6543/postgres"
            )
        )
