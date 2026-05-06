"""Dataset interfaces. Heavy frameworks imported lazily.

Cite docs/ml-architecture.md §10. Audio shot timestamps weakly-supervise
clip boundaries; the diagnostic head still needs expert labels but the
clip-extraction step does not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ShootingClip:
    """A ±2s window around a detected shot.

    Carries the consent flags and provenance needed for compliance-aware
    data loading (ml-architecture.md §10 last paragraph).
    """

    clip_path: str
    session_id: str
    athlete_id: str
    consent_version: str
    ml_training_consent: bool
    captured_at: str  # ISO-8601
    shot_index_in_session: int
    weakly_labeled: bool


class ShootingClipDataset(Protocol):
    """Iteration protocol used by training scripts.

    The compliance filter (consent + exclusion list) is applied at the
    data-loader layer, NOT the application layer — see ml-architecture.md
    §10 ("compliance hard requirement, not a feature toggle").
    """

    def __len__(self) -> int: ...
    def __iter__(self) -> ShootingClipDataset: ...
    def __next__(self) -> ShootingClip: ...


def filter_clips_for_training(
    clips: Sequence[ShootingClip],
    excluded_hashes: set[str],
    *,
    sample_hash_fn: object | None = None,  # callable(ShootingClip) -> str; injected by caller
) -> list[ShootingClip]:
    """Apply the consent + exclusion-list filter.

    Always require ``ml_training_consent``; drop anything in the exclusion
    list. Callers pass a hash function so this module doesn't need to know
    how sample identity is computed (clip path? content hash? both?).
    """
    if sample_hash_fn is None:
        return [c for c in clips if c.ml_training_consent]
    fn = sample_hash_fn  # for mypy: callable narrowed at runtime
    out: list[ShootingClip] = []
    for c in clips:
        if not c.ml_training_consent:
            continue
        h = fn(c)  # type: ignore[operator]
        if h in excluded_hashes:
            continue
        out.append(c)
    return out
