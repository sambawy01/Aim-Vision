"""Sprint 6 EPIC 6.1: audio shot detector classical baseline + eval harness.

Synthetic data only — no recorded range audio required. The numbers here
are the algorithmic floor the upcoming CRNN must beat.
"""

from __future__ import annotations

import numpy as np

from aimvision_ml.eval.audio_detection_eval import evaluate
from aimvision_ml.eval.synth_audio import SynthEvent, synth_clip
from aimvision_ml.inference.audio_shot import (
    ShotEvent,
    SpectralFluxConfig,
    SpectralFluxOnsetDetector,
    StubAudioShotDetector,
)


def test_stub_detector_returns_one_event_at_loudest_hop() -> None:
    sr = 48_000
    pcm = np.zeros(sr, dtype=np.float32)  # 1 s
    pcm[sr // 2 : sr // 2 + 100] = 0.9  # loud burst in the middle
    events = StubAudioShotDetector().detect(pcm, sr)
    assert len(events) == 1
    assert 0.45 <= events[0].timestamp_s <= 0.55


def test_spectral_flux_finds_isolated_shot() -> None:
    """A single muzzle blast in 2 s of pink noise must be recovered with
    timing error well under the 50 ms tolerance."""
    clip = synth_clip(
        duration_s=2.0,
        n_shots=1,
        n_clay=0,
        rng=np.random.default_rng(42),
    )
    events = SpectralFluxOnsetDetector().detect(clip.pcm, clip.sample_rate)
    truth = [e for e in clip.events if e.kind == "shot"]
    assert len(truth) == 1

    report = evaluate(events, clip.events, tolerance_ms=50.0)
    assert report.true_positives == 1
    assert report.false_negatives == 0


def test_spectral_flux_recall_on_multi_shot_clip() -> None:
    """Recall on a clip with 5 shots and 5 clay-impact distractors must
    hit the Sprint 6 floor (≥0.8 — the CRNN target is 0.95 but the
    classical baseline gives us the lower bound)."""
    clip = synth_clip(
        duration_s=8.0,
        n_shots=5,
        n_clay=5,
        rng=np.random.default_rng(123),
    )
    events = SpectralFluxOnsetDetector().detect(clip.pcm, clip.sample_rate)
    report = evaluate(events, clip.events, tolerance_ms=50.0)
    assert report.recall >= 0.8, f"recall {report.recall:.2f} below floor"


def test_spectral_flux_rejects_pure_wind() -> None:
    """A clip with no shots and no clays must produce zero detections
    (FPR floor). Wind alone should not trigger."""
    clip = synth_clip(
        duration_s=5.0,
        n_shots=0,
        n_clay=0,
        rng=np.random.default_rng(7),
    )
    events = SpectralFluxOnsetDetector().detect(clip.pcm, clip.sample_rate)
    assert len(events) == 0, f"got {len(events)} false positives on pure wind"


def test_min_gap_suppresses_double_trigger() -> None:
    """Two impulses 50 ms apart (under the 120 ms min_gap default) must
    collapse to a single detection — a real shotgun blast can ring the
    mic for a few hops; we should not double-count."""
    sr = 48_000
    pcm = np.zeros(int(sr * 1.0), dtype=np.float32)
    impulse = np.zeros(960, dtype=np.float32)
    impulse[0] = 0.9
    # Two near-coincident pings at 0.30s and 0.35s.
    pcm[int(0.30 * sr) : int(0.30 * sr) + 960] = impulse
    pcm[int(0.35 * sr) : int(0.35 * sr) + 960] = impulse
    events = SpectralFluxOnsetDetector(SpectralFluxConfig(min_gap_s=0.12)).detect(pcm, sr)
    assert len(events) == 1


def test_detector_rejects_empty_and_short_input() -> None:
    det = SpectralFluxOnsetDetector()
    assert det.detect(np.zeros(0, dtype=np.float32), 48_000) == []
    assert det.detect(np.zeros(8, dtype=np.float32), 48_000) == []


def test_evaluate_handles_clay_as_distractor_not_truth() -> None:
    """A prediction near a clay event but with no nearby shot is a false
    positive, not a true positive — clays are confounders, not targets."""
    truth = [SynthEvent(timestamp_s=1.0, kind="clay")]
    preds = [ShotEvent(timestamp_s=1.005, confidence=0.9, chunk_index=100)]
    report = evaluate(preds, truth, tolerance_ms=50.0)
    assert report.true_positives == 0
    assert report.false_positives == 1
    assert report.false_negatives == 0


def test_evaluate_pairs_each_truth_at_most_once() -> None:
    """Two predictions on the same truth event ≠ 2 TP — the second one
    is a duplicate FP. Greedy matching enforces 1:1."""
    truth = [SynthEvent(timestamp_s=1.0, kind="shot")]
    preds = [
        ShotEvent(timestamp_s=1.005, confidence=0.9, chunk_index=100),
        ShotEvent(timestamp_s=1.010, confidence=0.7, chunk_index=101),
    ]
    report = evaluate(preds, truth, tolerance_ms=50.0)
    assert report.true_positives == 1
    assert report.false_positives == 1
