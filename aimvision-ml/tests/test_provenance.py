"""Provenance filter: consent + exclusion list."""

from __future__ import annotations

from datetime import UTC, datetime

from aimvision_ml.data.provenance import ProvenanceRecord, filter_for_training


def _record(
    *,
    athlete_id: str = "a-1",
    sample_hash: str = "a" * 64,
    consent: bool = True,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        athlete_id=athlete_id,
        session_id="s-1",
        sample_path=f"/data/{sample_hash[:8]}.mp4",
        sample_hash=sample_hash,
        consent_version="2026-01-01",
        ml_training_consent=consent,
        captured_at=datetime.now(UTC),
        source="hero13",
    )


def test_filter_drops_no_consent() -> None:
    keep = _record(sample_hash="a" * 64, consent=True)
    drop = _record(sample_hash="b" * 64, consent=False)
    out = filter_for_training([keep, drop])
    assert out == [keep]


def test_filter_drops_excluded_hashes() -> None:
    keep = _record(sample_hash="c" * 64, consent=True)
    drop = _record(sample_hash="d" * 64, consent=True)
    out = filter_for_training([keep, drop], excluded_hashes={drop.sample_hash})
    assert out == [keep]


def test_filter_combines_both_drops() -> None:
    a = _record(sample_hash="e" * 64, consent=True)
    b = _record(sample_hash="f" * 64, consent=False)
    c = _record(sample_hash="0" * 64, consent=True)
    out = filter_for_training([a, b, c], excluded_hashes={c.sample_hash})
    assert out == [a]


def test_filter_empty_input_is_empty() -> None:
    assert filter_for_training([]) == []
