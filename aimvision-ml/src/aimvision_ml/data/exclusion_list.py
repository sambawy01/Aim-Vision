"""Append-only exclusion list for the right-to-erasure ML retraining path.

Cite the right-to-erasure architecture doc (compliance/right-to-erasure-
architecture.md) and ml-architecture.md §10. The list is one
sample-hash per line; the ML re-training data loader checks this on
every sample. Append-only by convention so we get a tamper-evident audit
trail; entries are not rewritten in place.
"""

from __future__ import annotations

import re
from pathlib import Path

_HASH_RE = re.compile(r"^[0-9a-f]{32,128}$")


class ExclusionList:
    """File-backed exclusion list. Idempotent `add`, O(1)-ish `contains`."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._cache: set[str] | None = None

    def _load(self) -> set[str]:
        if self._cache is not None:
            return self._cache
        cache: set[str] = set()
        with self.path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if not _HASH_RE.fullmatch(line):
                    raise ValueError(f"corrupt exclusion list: line {line!r} is not a hex hash")
                cache.add(line)
        self._cache = cache
        return cache

    def add(self, sample_hash: str) -> None:
        """Append a hash. Idempotent — duplicate adds are no-ops."""
        if not _HASH_RE.fullmatch(sample_hash):
            raise ValueError("sample_hash must be lowercase hex, 32–128 chars")
        cache = self._load()
        if sample_hash in cache:
            return
        # Append-only.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(sample_hash + "\n")
        cache.add(sample_hash)

    def contains(self, sample_hash: str) -> bool:
        """O(1)-after-load membership check."""
        return sample_hash in self._load()

    def count(self) -> int:
        """Number of distinct excluded hashes."""
        return len(self._load())

    def reload(self) -> None:
        """Force re-read from disk (used by long-running training jobs)."""
        self._cache = None
        self._load()
