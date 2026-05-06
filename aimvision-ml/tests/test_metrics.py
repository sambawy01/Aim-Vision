"""ECE / Brier / macro-F1 / conformal coverage tests on synthetic data."""

from __future__ import annotations

import numpy as np
import pytest

from aimvision_ml.eval.metrics import (
    brier_score,
    conformal_coverage,
    expected_calibration_error,
    macro_f1,
    top_k_macro_f1,
)


def test_perfect_predictions_have_zero_ece_and_brier() -> None:
    n, c = 200, 4
    rng = np.random.default_rng(42)
    labels = rng.integers(0, c, size=n)
    probs = np.zeros((n, c))
    probs[np.arange(n), labels] = 1.0
    assert expected_calibration_error(probs, labels) == pytest.approx(0.0, abs=1e-9)
    assert brier_score(probs, labels) == pytest.approx(0.0, abs=1e-9)


def test_uniform_predictions_have_high_ece_when_unbalanced() -> None:
    # All predictions confident wrong: confidence 1.0, accuracy 0.0 → ECE = 1.0.
    n, c = 100, 3
    labels = np.zeros(n, dtype=np.int64)
    probs = np.zeros((n, c))
    probs[:, 1] = 1.0  # always predict class 1
    ece = expected_calibration_error(probs, labels)
    assert ece == pytest.approx(1.0, abs=1e-9)


def test_brier_bounded_between_zero_and_two() -> None:
    rng = np.random.default_rng(1)
    n, c = 50, 5
    logits = rng.normal(size=(n, c))
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    labels = rng.integers(0, c, size=n)
    val = brier_score(probs, labels)
    assert 0.0 <= val <= 2.0


def test_macro_f1_perfect_is_one() -> None:
    labels = np.array([0, 1, 2, 0, 1, 2])
    preds = labels.copy()
    assert macro_f1(preds, labels, n_classes=3) == pytest.approx(1.0)


def test_macro_f1_zero_when_all_predictions_wrong() -> None:
    labels = np.array([0, 1, 2, 0, 1, 2])
    preds = (labels + 1) % 3
    f1 = macro_f1(preds, labels, n_classes=3)
    assert f1 == pytest.approx(0.0)


def test_macro_f1_class_with_no_support_does_not_crash() -> None:
    labels = np.array([0, 0, 1, 1])
    preds = np.array([0, 0, 1, 1])
    # n_classes=4 even though only 0 and 1 appear.
    f1 = macro_f1(preds, labels, n_classes=4)
    # Two classes perfect, two classes f1=0 → macro = 0.5.
    assert f1 == pytest.approx(0.5)


def test_top_k_macro_f1_at_least_top_1() -> None:
    rng = np.random.default_rng(7)
    n, c = 80, 5
    logits = rng.normal(size=(n, c))
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    labels = rng.integers(0, c, size=n)
    f1_top1 = top_k_macro_f1(probs, labels, k=1, n_classes=c)
    f1_top3 = top_k_macro_f1(probs, labels, k=3, n_classes=c)
    assert f1_top3 >= f1_top1 - 1e-9


def test_conformal_coverage_basic() -> None:
    sets: list[set[int]] = [{0, 1}, {2}, {1, 2}, {0}]
    labels = np.array([0, 2, 3, 1])
    # Covered: idx 0 (0 in {0,1}), idx 1 (2 in {2}). Not covered: 2, 3.
    assert conformal_coverage(sets, labels) == pytest.approx(0.5)


def test_conformal_coverage_full_coverage() -> None:
    sets: list[list[int]] = [[0, 1, 2]] * 4
    labels = np.array([0, 1, 2, 0])
    assert conformal_coverage(sets, labels) == pytest.approx(1.0)


def test_ece_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError):
        expected_calibration_error(np.zeros(10), np.zeros(10))
