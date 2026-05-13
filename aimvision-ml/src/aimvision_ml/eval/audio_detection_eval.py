"""Audio shot-detection eval harness.

Sprint 6 EPIC 6.1. Matches detector outputs to ground-truth shot events
inside a configurable tolerance window and reports precision/recall/F1
plus mean timing error. The CI gate (`gates.py`) consumes this struct.
"""

from __future__ import annotations

from dataclasses import dataclass

from aimvision_ml.eval.synth_audio import SynthEvent
from aimvision_ml.inference.audio_shot import ShotEvent


@dataclass(frozen=True)
class DetectionReport:
    precision: float
    recall: float
    f1: float
    mean_timing_error_ms: float
    false_positives: int
    false_negatives: int
    true_positives: int


def evaluate(
    predicted: list[ShotEvent],
    truth: list[SynthEvent],
    *,
    tolerance_ms: float = 50.0,
) -> DetectionReport:
    """Greedy 1:1 match between predictions and shot-kind truth events.

    Each prediction is paired with the nearest unused truth event within
    `tolerance_ms`. Truth events that are not "shot" (clay, wind_gust)
    do not consume a prediction — they are confounders, and a prediction
    near them counts as a false positive. This is the right scoring for
    the detector's job (find muzzle blasts, ignore everything else).
    """
    if tolerance_ms <= 0:
        raise ValueError("tolerance_ms must be positive")

    shot_truth = [t for t in truth if t.kind == "shot"]
    tol_s = tolerance_ms / 1000.0

    matched_truth_idx: set[int] = set()
    matches: list[tuple[int, int]] = []  # (pred_idx, truth_idx)

    sorted_preds = sorted(range(len(predicted)), key=lambda i: predicted[i].timestamp_s)
    for pi in sorted_preds:
        ts = predicted[pi].timestamp_s
        best_t = -1
        best_d = tol_s
        for ti, te in enumerate(shot_truth):
            if ti in matched_truth_idx:
                continue
            d = abs(te.timestamp_s - ts)
            if d <= best_d:
                best_d = d
                best_t = ti
        if best_t >= 0:
            matched_truth_idx.add(best_t)
            matches.append((pi, best_t))

    tp = len(matches)
    fp = len(predicted) - tp
    fn = len(shot_truth) - tp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    if matches:
        errs = [
            abs(predicted[pi].timestamp_s - shot_truth[ti].timestamp_s) * 1000.0
            for pi, ti in matches
        ]
        mean_err = sum(errs) / len(errs)
    else:
        mean_err = 0.0

    return DetectionReport(
        precision=precision,
        recall=recall,
        f1=f1,
        mean_timing_error_ms=mean_err,
        false_positives=fp,
        false_negatives=fn,
        true_positives=tp,
    )
