"""Stratified evaluation buckets.

Cite docs/ml-architecture.md §12: every promotion runs the bias audit
across station, discipline, lighting, body type, skin tone, clothing color.
A bias gap > 0.05 macro-F1 on any axis fails promotion.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Stratum:
    """One slice of the eval set."""

    axis: str
    bucket: str
    sample_indices: tuple[int, ...]


# Default axes per ml-architecture.md §12. Concrete buckets are dataset-
# dependent; this module just helps construct strata from per-sample
# metadata dicts.
DEFAULT_STRATIFICATION_AXES: tuple[str, ...] = (
    "station",
    "discipline",
    "lighting",
    "body_type",
    "skin_tone",
    "clothing_color",
)


def stratify(
    metadata: Sequence[dict[str, object]],
    axes: Iterable[str] = DEFAULT_STRATIFICATION_AXES,
) -> list[Stratum]:
    """Group sample indices by ``(axis, bucket)``.

    `metadata[i]` is a dict with at least the requested axis keys; missing
    values are bucketed as ``"unknown"`` so they aren't silently dropped
    from the audit (silent drops would hide bias gaps).
    """
    out: list[Stratum] = []
    for axis in axes:
        buckets: dict[str, list[int]] = {}
        for i, meta in enumerate(metadata):
            val = meta.get(axis, "unknown")
            key = str(val) if val is not None else "unknown"
            buckets.setdefault(key, []).append(i)
        for bucket, idxs in sorted(buckets.items()):
            out.append(Stratum(axis=axis, bucket=bucket, sample_indices=tuple(idxs)))
    return out


def axis_buckets(strata: Iterable[Stratum], axis: str) -> list[Stratum]:
    """All strata for a given axis, in declaration order."""
    return [s for s in strata if s.axis == axis]
