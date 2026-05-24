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

    # Identity provider switch (ADR-0010). "stub" keeps the in-house
    # PBKDF2 + HS256 path that ships today; "gotrue" routes login
    # through a self-hosted Supabase Auth (GoTrue) JWT verifier. The
    # `/auth/login` integration that consumes a GoTrue token lands in
    # a follow-up PR; this flag exists so the verifier module can be
    # exercised in tests and dual-run during cutover without a code
    # change.
    auth_provider: str = "stub"
    # Issuer claim that GoTrue stamps into its JWTs. Must be set when
    # `auth_provider == "gotrue"`. For a default Supabase Auth self-host
    # this is the `GOTRUE_JWT_ISS` env or the project URL.
    gotrue_issuer: str | None = None
    # Audience the verifier requires. GoTrue defaults to "authenticated"
    # for end-user tokens; service-role tokens use "service_role" and
    # must never reach end-user endpoints.
    gotrue_audience: str = "authenticated"
    # HS256 path: shared secret with the GoTrue process
    # (`GOTRUE_JWT_SECRET`). Required when `gotrue_jwt_alg == "HS256"`.
    gotrue_jwt_secret: str | None = None
    # Asymmetric path: PEM-encoded public key. Required when
    # `gotrue_jwt_alg` is RS256/RS384/RS512/ES256/ES384.
    gotrue_jwt_public_key_pem: str | None = None
    gotrue_jwt_alg: str = "HS256"

    # Key Encryption Key for per-tenant DEK wrapping (right-to-erasure
    # crypto-shred, services/crypto_shred.py). Production roots this in
    # AWS KMS / Vault; here it's a config secret SHA-256'd to 32 bytes.
    data_encryption_kek: str = "dev-data-encryption-kek-change-me-in-production"

    # Dev defaults cover both the legacy :3000 and the Vite dev server (:5173)
    # the web app actually runs on. Production overrides via AIMVISION_CORS_ORIGINS.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
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

    # Base URL the Temporal post-session worker uses to call the
    # backend API (ADR-0007). Empty (the dev/test default) keeps the
    # finalize activity in stub mode — it logs and returns without a
    # real HTTP call. Set to the in-cluster API URL in production so
    # the worker actually persists the session-end transition.
    post_session_base_url: str = ""
    # Subject (`sub`) for the worker's minted service token. Signed
    # with the same `jwt_secret`, so no external IdP is needed for the
    # same-trust-domain worker→API call.
    post_session_worker_user_id: str = "post-session-worker"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+asyncpg://"))

    @property
    def effective_audit_database_url(self) -> str:
        return self.audit_database_url or self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
