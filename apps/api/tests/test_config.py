import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_ephemeral_configuration():
    with pytest.raises(ValidationError, match="demo authentication is disabled"):
        Settings(_env_file=None, app_env="production")


def test_complete_production_configuration_is_accepted():
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://user:password@example.test/complyscan",
        allow_memory_fallback=False,
        auth_mode="jwt",
        auth_issuer="https://issuer.example.test",
        auth_audience="complyscan",
        auth_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        vision_provider="gemini",
        gemini_api_key="server-secret",
        blob_read_write_token="blob-secret",
    )
    assert settings.app_env == "production"
    assert settings.allow_memory_fallback is False
