"""Recording storage abstraction — ADR-0009 slice 2.

The Storage protocol lets a single recording-upload handler write to
either local filesystem (dev / tests) or, in a later slice, S3 / GCS /
the federation appliance's on-prem object store. Slice 2 ships only
the LocalFsStorage impl.

Returned URI convention:
    local://{tenant_id}/{session_id}/{recording_id}.mp4
    s3://{bucket}/{key}                                  (future)
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile, status

from ..config import get_settings


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Result of a successful upload."""

    storage_uri: str
    """Canonical scheme-qualified URI; the backend can resolve it back to bytes."""
    size_bytes: int
    """Total bytes written. Sourced from the upload stream, not stat() — the latter
    is a separate syscall that could race with the writer on networked filesystems."""
    sha256_hex: str
    """sha256 of the uploaded bytes, computed incrementally as we stream."""


# Chunk size for the streaming write loop. Tuned for two concerns: small
# enough that one chunk in flight is bounded RAM, large enough that the
# per-chunk syscall overhead doesn't dominate on big files. 1 MiB hits
# the sweet spot for typical session-length recordings (10s of MB to a
# few GB).
_CHUNK_BYTES = 1 * 1024 * 1024


class Storage(Protocol):
    async def store_upload(
        self,
        *,
        upload: UploadFile,
        tenant_id: str,
        session_id: str,
        recording_id: str,
        max_bytes: int,
    ) -> StoredObject: ...


class LocalFsStorage:
    """Filesystem storage backend. Writes streamed chunks under
    ``{base_dir}/{tenant_id}/{session_id}/{recording_id}.mp4``."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)

    async def store_upload(
        self,
        *,
        upload: UploadFile,
        tenant_id: str,
        session_id: str,
        recording_id: str,
        max_bytes: int,
    ) -> StoredObject:
        # Tenant/session/recording IDs are server-controlled — they come from
        # the DB row, not the client — so we can safely use them in the path
        # without sanitization concerns. Still defensive-check for traversal.
        for segment in (tenant_id, session_id, recording_id):
            if "/" in segment or ".." in segment:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="invalid storage path segment",
                )
        target_dir = self._base_dir / tenant_id / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{recording_id}.mp4"

        sha = hashlib.sha256()
        written = 0
        # Synchronous file IO is OK here: the chunks come off the
        # in-memory SpooledTemporaryFile (already spooled by Starlette)
        # and disk writes return in microseconds. If this ever ends up
        # behind a slow network filesystem, swap to aiofiles.
        with target_path.open("wb") as f:
            async for chunk in _read_in_chunks(upload):
                written += len(chunk)
                if written > max_bytes:
                    # Clean up the partial file so we don't leak disk on
                    # repeated oversized attempts.
                    f.close()
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"recording exceeds max size of {max_bytes} bytes",
                    )
                f.write(chunk)
                sha.update(chunk)

        if written == 0:
            target_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="empty upload",
            )

        return StoredObject(
            storage_uri=f"local://{tenant_id}/{session_id}/{recording_id}.mp4",
            size_bytes=written,
            sha256_hex=sha.hexdigest(),
        )


async def _read_in_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload.read(_CHUNK_BYTES)
        if not chunk:
            return
        yield chunk


_storage_singleton: Storage | None = None


def get_storage() -> Storage:
    """FastAPI dependency entrypoint. Returns a process-wide singleton
    bound to the current settings; tests reset it via `set_storage` to
    point at a per-test tmp_path."""
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = LocalFsStorage(get_settings().storage_base_dir)
    return _storage_singleton


def set_storage(storage: Storage | None) -> None:
    """Test hook. Pass None to clear the cache so the next get_storage()
    re-reads settings."""
    global _storage_singleton
    _storage_singleton = storage
