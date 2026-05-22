"""Per-tenant envelope encryption + crypto-shred tests.

The load-bearing erasure property (right-to-erasure-architecture.md
§2.3): destroying the DEK makes the tenant's data permanently
undecryptable, and a shredded tenant can never be re-keyed.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.services import crypto_shred
from app.services.crypto_shred import DekShreddedError


def _sm() -> async_sessionmaker:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False)


@pytest.mark.asyncio
async def test_encrypt_decrypt_round_trip(db_schema: None) -> None:
    async with _sm()() as s, s.begin():
        blob = await crypto_shred.encrypt_for_tenant(s, "solo:t-rt", b"pose-keypoints")
        assert blob != b"pose-keypoints"
        out = await crypto_shred.decrypt_for_tenant(s, "solo:t-rt", blob)
        assert out == b"pose-keypoints"


@pytest.mark.asyncio
async def test_shred_makes_data_undecryptable(db_schema: None) -> None:
    async with _sm()() as s, s.begin():
        blob = await crypto_shred.encrypt_for_tenant(s, "solo:t-shred", b"secret")
        await crypto_shred.shred_tenant_dek(s, "solo:t-shred")
        with pytest.raises(DekShreddedError):
            await crypto_shred.decrypt_for_tenant(s, "solo:t-shred", blob)


@pytest.mark.asyncio
async def test_shredded_tenant_cannot_be_rekeyed(db_schema: None) -> None:
    """ensure_tenant_dek must refuse to resurrect a shredded tenant —
    otherwise erasure would be reversible."""
    async with _sm()() as s, s.begin():
        await crypto_shred.ensure_tenant_dek(s, "solo:t-rekey")
        await crypto_shred.shred_tenant_dek(s, "solo:t-rekey")
        with pytest.raises(DekShreddedError):
            await crypto_shred.ensure_tenant_dek(s, "solo:t-rekey")


@pytest.mark.asyncio
async def test_shred_without_prior_key_writes_tombstone(db_schema: None) -> None:
    async with _sm()() as s, s.begin():
        await crypto_shred.shred_tenant_dek(s, "solo:t-never-keyed")
        # A subsequent encrypt must fail: the tombstone blocks re-keying.
        with pytest.raises(DekShreddedError):
            await crypto_shred.encrypt_for_tenant(s, "solo:t-never-keyed", b"x")


@pytest.mark.asyncio
async def test_blob_is_bound_to_tenant(db_schema: None) -> None:
    """A blob sealed for one tenant cannot be decrypted as another
    (tenant_id is the AES-GCM associated data)."""
    async with _sm()() as s, s.begin():
        blob = await crypto_shred.encrypt_for_tenant(s, "solo:t-a", b"data")
        await crypto_shred.ensure_tenant_dek(s, "solo:t-b")
        with pytest.raises(DekShreddedError):
            await crypto_shred.decrypt_for_tenant(s, "solo:t-b", blob)
