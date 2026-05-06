"""Gate tests: passes on clean synthetic preds, fails on miscalibrated ones."""

from __future__ import annotations

import numpy as np

from aimvision_ml.eval.gates import GateThresholds, evaluate


def _make_clean_preds(
    n: int = 600,
    c: int = 5,
    seed: int = 0,
    correct_prob: float = 0.92,
) -> tuple[np.ndarray, np.ndarray, list[set[int]]]:
    """Build well-calibrated predictions with high macro-F1.

    For each sample, the predicted top-1 confidence is `correct_prob` and
    the model is correct with the same probability — the canonical
    well-calibrated synthetic distribution. Conformal sets always include
    the true label so coverage is 1.0.
    """
    rng = np.random.default_rng(seed)
    true_labels = rng.integers(0, c, size=n)
    correct_mask = rng.random(n) < correct_prob
    # When correct: predicted argmax is the true label.
    # When wrong: predicted argmax is some other class.
    predicted = true_labels.copy()
    if c > 1:
        wrong_idx = np.where(~correct_mask)[0]
        offsets = rng.integers(1, c, size=wrong_idx.size)
        predicted[wrong_idx] = (true_labels[wrong_idx] + offsets) % c
    probs = np.full((n, c), (1.0 - correct_prob) / (c - 1), dtype=np.float64)
    probs[np.arange(n), predicted] = correct_prob
    sets = [{int(lbl)} for lbl in true_labels]
    return probs, true_labels, sets


def test_gate_passes_on_clean_preds() -> None:
    probs, labels, sets = _make_clean_preds()
    result = evaluate(probs, labels, n_classes=5, prediction_sets=sets)
    assert result.passed, result.notes
    assert result.ece <= 0.05
    assert result.top3_macro_f1 >= 0.78
    assert result.conformal_coverage >= 0.88


def test_gate_fails_on_miscalibrated_preds() -> None:
    n, c = 400, 5
    rng = np.random.default_rng(1)
    labels = rng.integers(0, c, size=n)
    # Always predict class 0 with probability 0.99 → ECE near 1 - 1/c.
    probs = np.full((n, c), 0.0025, dtype=np.float64)
    probs[:, 0] = 0.99
    sets = [{0} for _ in range(n)]  # rarely covers the true label
    result = evaluate(probs, labels, n_classes=c, prediction_sets=sets)
    assert not result.passed
    assert "ECE" in result.notes or "top3" in result.notes


def test_gate_flags_bias_axis_when_gap_exceeds_threshold() -> None:
    # 2 buckets: one perfect, one all-wrong → macro-F1 spread = 1.0.
    n_per = 50
    c = 3
    metadata: list[dict[str, object]] = []
    probs_rows: list[np.ndarray] = []
    labels_list: list[int] = []
    for _ in range(n_per):
        probs_rows.append(np.eye(c)[0])
        labels_list.append(0)
        metadata.append({"lighting": "good"})
    for _ in range(n_per):
        # Wrong predictions.
        row = np.zeros(c)
        row[1] = 1.0
        probs_rows.append(row)
        labels_list.append(0)
        metadata.append({"lighting": "harsh_sun"})
    probs = np.stack(probs_rows)
    labels = np.array(labels_list)
    sets = [{int(lbl)} for lbl in labels]
    result = evaluate(probs, labels, n_classes=c, prediction_sets=sets, metadata=metadata)
    assert not result.passed
    assert any("lighting" in axis for axis in result.failed_axes)


def test_gate_thresholds_can_be_relaxed() -> None:
    probs, labels, sets = _make_clean_preds(correct_prob=0.6)  # weak preds
    relaxed = GateThresholds(
        ece_max=0.5,
        top3_macro_f1_min=0.0,
        conformal_coverage_min=0.0,
        bias_axis_macro_f1_gap_max=1.0,
    )
    result = evaluate(probs, labels, n_classes=5, prediction_sets=sets, thresholds=relaxed)
    assert result.passed
