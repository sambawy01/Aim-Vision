"""Runtime configuration via Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIMVISION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    version: str = "0.1.0"
    git_sha: str = "dev"

    database_url: str = "sqlite+aiosqlite:///./aimvision.db"
    audit_database_url: str | None = None

    jwt_secret: str = "dev-secret-change-me-in-production-please-32"
    jwt_alg: str = "HS256"
    jwt_ttl_seconds: int = 3600

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    ip_hash_salt: str = "dev-salt-rotate-daily"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+asyncpg://"))

    @property
    def effective_audit_database_url(self) -> str:
        return self.audit_database_url or self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
