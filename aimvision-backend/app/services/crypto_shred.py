"""Per-tenant envelope encryption + crypto-shredding.

The load-bearing erasure primitive (right-to-erasure-architecture.md
§2): every tenant has a Data Encryption Key (DEK); tenant data at rest
is encrypted under it; destroying the DEK ("crypto-shred") renders all
copies — including encrypted backups — permanently undecryptable.

Key hierarchy (§2.1-§2.2):

    KEK (per-region, KMS/Vault-rooted in prod; config-derived here)
      └─ wraps ─> per-tenant DEK (stored wrapped in tenant_encryption_keys)
                    └─ encrypts ─> tenant data at rest

In production the KEK lives in AWS KMS / Vault. Here it is derived
from `settings.data_encryption_kek` so the same code path is testable
without a cloud dependency; the wrapping/unwrapping seam is identical.

Wire format for both wrapped DEKs and ciphertext blobs:
`12-byte nonce || AES-256-GCM ciphertext+tag`. The tenant_id is bound
as AES-GCM associated data so a blob can't be replayed across tenants.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.erasure import TenantEncryptionKey

_NONCE_LEN = 12


class DekShreddedError(RuntimeError):
    """Raised when a tenant's DEK is missing or has been shredded.

    Either the tenant was never keyed, or its data has been
    crypto-shredded by a fulfilled erasure request — in both cases the
    data is (or should be treated as) permanently undecryptable.
    """


def _kek() -> bytes:
    """Derive the 32-byte Key Encryption Key from configuration.

    Production roots this in KMS/Vault; we SHA-256 the configured
    secret so any-length secret yields a valid AES-256 key and the
    call site stays identical.
    """
    return hashlib.sha256(get_settings().data_encryption_kek.encode("utf-8")).digest()


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, aad)


async def ensure_tenant_dek(db: AsyncSession, tenant_id: str) -> None:
    """Create the tenant's DEK if absent. Idempotent.

    Refuses to re-create a DEK for a tenant that has been shredded —
    re-keying would un-shred the data and break the erasure guarantee.
    Callers that hit a shredded tenant get `DekShreddedError`.
    """
    row = await db.get(TenantEncryptionKey, tenant_id)
    if row is not None:
        if row.shredded_at is not None:
            raise DekShreddedError(
                f"tenant {tenant_id} has been crypto-shredded; refusing to re-key"
            )
        return
    dek = AESGCM.generate_key(bit_length=256)
    wrapped = _seal(_kek(), dek, tenant_id.encode("utf-8"))
    db.add(
        TenantEncryptionKey(
            tenant_id=tenant_id,
            key_version=1,
            wrapped_dek=wrapped,
            created_at=datetime.now(UTC),
        )
    )
    await db.flush()


async def _unwrap_dek(db: AsyncSession, tenant_id: str) -> bytes:
    row = await db.get(TenantEncryptionKey, tenant_id)
    if row is None or row.shredded_at is not None or row.wrapped_dek is None:
        raise DekShreddedError(f"no usable DEK for tenant {tenant_id}")
    try:
        return _open(_kek(), row.wrapped_dek, tenant_id.encode("utf-8"))
    except InvalidTag as exc:  # pragma: no cover - wrong KEK / corrupted store
        raise DekShreddedError(f"DEK for tenant {tenant_id} failed to unwrap") from exc


async def encrypt_for_tenant(db: AsyncSession, tenant_id: str, plaintext: bytes) -> bytes:
    """Encrypt a blob under the tenant's DEK. Auto-keys the tenant."""
    await ensure_tenant_dek(db, tenant_id)
    dek = await _unwrap_dek(db, tenant_id)
    return _seal(dek, plaintext, tenant_id.encode("utf-8"))


async def decrypt_for_tenant(db: AsyncSession, tenant_id: str, blob: bytes) -> bytes:
    """Decrypt a blob. Raises `DekShreddedError` once the tenant is shredded."""
    dek = await _unwrap_dek(db, tenant_id)
    try:
        return _open(dek, blob, tenant_id.encode("utf-8"))
    except InvalidTag as exc:
        raise DekShreddedError(f"blob for tenant {tenant_id} failed to decrypt") from exc


async def shred_tenant_dek(db: AsyncSession, tenant_id: str) -> None:
    """Destroy the tenant's DEK. Irreversible.

    After this, every blob encrypted under the DEK — live rows,
    replicas, and encrypted backups — is undecryptable. If the tenant
    was never keyed, a shredded tombstone row is still written so a
    later `ensure_tenant_dek` cannot resurrect access.
    """
    row = await db.get(TenantEncryptionKey, tenant_id)
    now = datetime.now(UTC)
    if row is None:
        db.add(
            TenantEncryptionKey(
                tenant_id=tenant_id,
                key_version=1,
                wrapped_dek=None,
                created_at=now,
                shredded_at=now,
            )
        )
    else:
        row.wrapped_dek = None
        row.shredded_at = now
    await db.flush()
