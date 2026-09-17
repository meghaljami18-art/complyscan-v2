from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    service_name: str = "COMPLYSCAN API"
    database_url: str = ""
    allow_memory_fallback: bool = True

    auth_mode: str = "demo"
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    auth_algorithm: str = "RS256"

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    vision_provider: str = "fixture"
    vision_timeout_seconds: float = Field(default=90, ge=5, le=180)
    vision_max_attempts: int = Field(default=3, ge=1, le=5)
    vision_max_images: int = Field(default=6, ge=1, le=6)
    vision_max_inline_bytes: int = Field(default=12_000_000, ge=100_000, le=40_000_000)

    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    blob_read_write_token: SecretStr | None = None
    object_allowed_hosts: tuple[str, ...] = (".blob.vercel-storage.com",)

    ruleset_id: str = "LMPC_MVP"
    ruleset_version: str = "LMPC_2026_08_26"
    vercel_git_commit_sha: str | None = None
    max_request_bytes: int = Field(default=4_000_000, ge=100_000, le=4_400_000)

    @field_validator("app_env", "auth_mode", "vision_provider", mode="before")
    @classmethod
    def normalize_lower(cls, value: object) -> str:
        return str(value).strip().lower()

    @field_validator("cors_origins", "object_allowed_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def production_guards(self) -> "Settings":
        if self.auth_mode not in {"demo", "jwt"}:
            raise ValueError("AUTH_MODE must be demo or jwt")
        if self.vision_provider not in {"fixture", "gemini"}:
            raise ValueError("VISION_PROVIDER must be fixture or gemini")
        if self.app_env == "production":
            if self.auth_mode == "demo":
                raise ValueError("demo authentication is disabled in production")
            if not self.database_url:
                raise ValueError("production requires DATABASE_URL")
            if self.allow_memory_fallback:
                raise ValueError("ALLOW_MEMORY_FALLBACK must be false in production")
            if self.vision_provider != "gemini" or not self.gemini_api_key:
                raise ValueError("production requires VISION_PROVIDER=gemini and GEMINI_API_KEY")
            if not self.blob_read_write_token:
                raise ValueError("production requires a private Vercel Blob store")
        if self.auth_mode == "jwt" and not (self.auth_issuer and self.auth_audience and self.auth_jwks_url):
            raise ValueError("JWT authentication requires AUTH_ISSUER, AUTH_AUDIENCE, and AUTH_JWKS_URL")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
