"""Stratify tests: bucket construction and unknown-handling."""

from __future__ import annotations

from aimvision_ml.eval.stratify import (
    DEFAULT_STRATIFICATION_AXES,
    axis_buckets,
    stratify,
)


def _meta_grid() -> list[dict[str, object]]:
    return [
        {"station": "1", "lighting": "harsh_sun", "discipline": "skeet"},
        {"station": "1", "lighting": "good", "discipline": "skeet"},
        {"station": "7", "lighting": "good", "discipline": "skeet"},
        {"station": "7", "lighting": "harsh_sun", "discipline": "trap"},
        # missing station → bucketed as "unknown"
        {"lighting": "good", "discipline": "trap"},
    ]


def test_stratify_returns_one_stratum_per_axis_bucket() -> None:
    strata = stratify(_meta_grid())
    # Every axis is represented at least once.
    axes_seen = {s.axis for s in strata}
    assert axes_seen >= {"station", "lighting", "discipline"}


def test_unknown_bucket_is_explicit() -> None:
    strata = stratify(_meta_grid(), axes=["station"])
    buckets = {s.bucket for s in strata}
    assert "unknown" in buckets


def test_axis_buckets_helper_filters_correctly() -> None:
    strata = stratify(_meta_grid())
    station_strata = axis_buckets(strata, "station")
    for s in station_strata:
        assert s.axis == "station"


def test_default_axes_match_doc() -> None:
    # If this list ever drifts from ml-architecture.md §12, fail loudly.
    assert DEFAULT_STRATIFICATION_AXES == (
        "station",
        "discipline",
        "lighting",
        "body_type",
        "skin_tone",
        "clothing_color",
    )


def test_indices_partition_inputs_per_axis() -> None:
    meta = _meta_grid()
    strata = stratify(meta, axes=["lighting"])
    seen: set[int] = set()
    for s in strata:
        for idx in s.sample_indices:
            assert idx not in seen, "indices must be disjoint within an axis"
            seen.add(idx)
    assert seen == set(range(len(meta)))
