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

    # Key Encryption Key for per-tenant DEK wrapping (right-to-erasure
    # crypto-shred, services/crypto_shred.py). Production roots this in
    # AWS KMS / Vault; here it's a config secret SHA-256'd to 32 bytes.
    data_encryption_kek: str = "dev-data-encryption-kek-change-me-in-production"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    ip_hash_salt: str = "dev-salt-rotate-daily"

    # Local-fs storage backend root. Recording uploads land under
    # {storage_base_dir}/{tenant_id}/{session_id}/{recording_id}.mp4.
    # Slice 2 ships local-fs only; S3 / object-storage backends land
    # in a later slice via the Storage protocol in services/storage.py.
    storage_base_dir: str = "/tmp/aimvision-recordings"
    # Per-recording upload size ceiling, bytes. The router rejects any
    # request whose content length exceeds this; defensive against
    # mis-configured clients filling the disk.
    max_recording_upload_bytes: int = 4 * 1024 * 1024 * 1024  # 4 GiB

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+asyncpg://"))

    @property
    def effective_audit_database_url(self) -> str:
        return self.audit_database_url or self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
