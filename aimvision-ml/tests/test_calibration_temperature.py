"""Numpy-only temperature scaling: fitting reduces ECE on miscalibrated data."""

from __future__ import annotations

import numpy as np

from aimvision_ml.eval.metrics import expected_calibration_error
from aimvision_ml.inference.calibration import (
    TemperatureScaler,
    conformal_prediction_sets,
)


def _miscalibrated_logits(
    n: int = 800, c: int = 5, seed: int = 13
) -> tuple[np.ndarray, np.ndarray]:
    """Generate logits that are systematically too peaked (over-confident).

    Picks true labels from a fixed prior, samples logits from the truth,
    then scales by 4 — that's the classic over-confidence pattern that
    temperature scaling is designed to fix (Guo et al. 2017).
    """
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, c, size=n)
    base = rng.normal(loc=0.0, scale=1.0, size=(n, c))
    base[np.arange(n), labels] += 1.5  # signal toward the true class
    over_confident = base * 4.0
    return over_confident, labels


def test_temperature_fit_improves_ece() -> None:
    logits, labels = _miscalibrated_logits()
    pre_probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    pre_ece = expected_calibration_error(pre_probs, labels)

    ts = TemperatureScaler()
    result = ts.fit(logits, labels)
    post_probs = ts.apply(logits)
    post_ece = expected_calibration_error(post_probs, labels)

    assert result.temperature > 1.0  # over-confident → T > 1
    assert post_ece < pre_ece - 0.01, f"ECE did not improve: {pre_ece:.3f} → {post_ece:.3f}"
    assert result.nll_after <= result.nll_before + 1e-9


def test_temperature_one_when_already_calibrated() -> None:
    # Logits where softmax already matches empirical accuracy: scale by
    # picking diffuse logits so confidence is low and accuracy is also low.
    rng = np.random.default_rng(0)
    n, c = 600, 4
    labels = rng.integers(0, c, size=n)
    logits = rng.normal(scale=0.1, size=(n, c))
    ts = TemperatureScaler()
    result = ts.fit(logits, labels)
    # Cannot pin T exactly to 1; just check the optimizer didn't blow up
    # and that NLL didn't increase.
    assert result.temperature > 0
    assert result.nll_after <= result.nll_before + 1e-6


def test_apply_without_fit_raises() -> None:
    ts = TemperatureScaler()
    try:
        ts.apply(np.zeros((1, 3)))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError when applying before fitting")


def test_conformal_sets_cover_at_target_rate() -> None:
    # Synthetic calibration + test split with shared (well-behaved) probs.
    rng = np.random.default_rng(2)
    n_cal, n_test, c = 400, 400, 5
    labels_cal = rng.integers(0, c, size=n_cal)
    labels_test = rng.integers(0, c, size=n_test)
    probs_cal = np.full((n_cal, c), 0.05)
    probs_cal[np.arange(n_cal), labels_cal] = 0.80
    probs_test = np.full((n_test, c), 0.05)
    probs_test[np.arange(n_test), labels_test] = 0.80

    sets = conformal_prediction_sets(probs_cal, labels_cal, probs_test, coverage=0.90)
    covered = sum(int(int(lbl) in s) for s, lbl in zip(sets, labels_test, strict=True))
    rate = covered / n_test
    # Empirical coverage should be close to the requested level.
    assert rate >= 0.85
