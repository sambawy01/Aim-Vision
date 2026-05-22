"""Evaluation metrics — numpy only, no torch.

Calibration (ECE, Brier), classification (macro-F1), and conformal coverage.
Implementations are deliberately small and inspectable so the CI gate logic
in `gates.py` can be reasoned about end-to-end. Cite ml-architecture.md §12.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


def expected_calibration_error(
    probs: npt.ArrayLike,
    labels: npt.ArrayLike,
    n_bins: int = 15,
) -> float:
    """Expected Calibration Error (Guo et al. 2017) on top-1 predictions.

    `probs` is shape ``(N, C)`` softmax-normalized. `labels` is shape
    ``(N,)`` integer class ids. ECE is bucketed by max-probability and
    compares mean confidence to mean accuracy in each bucket.

    Returns a non-negative float; lower is better. Target ≤ 0.05 per task
    per ml-architecture.md §8.
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 2:
        raise ValueError(f"probs must be (N, C); got shape {probs_arr.shape}")
    if labels_arr.shape[0] != probs_arr.shape[0]:
        raise ValueError("probs and labels must agree on N")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")

    confidences = probs_arr.max(axis=1)
    predictions = probs_arr.argmax(axis=1)
    accuracies = (predictions == labels_arr).astype(np.float64)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = float(probs_arr.shape[0])
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        # Right-open except for the final bin to include conf == 1.0.
        if i == n_bins - 1:
            mask: BoolArray = (confidences >= lo) & (confidences <= hi)
        else:
            mask = (confidences >= lo) & (confidences < hi)
        bucket_n = int(mask.sum())
        if bucket_n == 0:
            continue
        avg_conf = float(confidences[mask].mean())
        avg_acc = float(accuracies[mask].mean())
        ece += (bucket_n / n) * abs(avg_conf - avg_acc)
    return float(ece)


def brier_score(
    probs: npt.ArrayLike,
    labels: npt.ArrayLike,
) -> float:
    """Multiclass Brier score: mean squared error against one-hot labels.

    Lower is better; bounded in ``[0, 2]`` for K-class one-hot.
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 2:
        raise ValueError(f"probs must be (N, C); got {probs_arr.shape}")
    n, c = probs_arr.shape
    if labels_arr.shape[0] != n:
        raise ValueError("probs and labels must agree on N")
    one_hot = np.zeros((n, c), dtype=np.float64)
    one_hot[np.arange(n), labels_arr] = 1.0
    return float(np.mean(np.sum((probs_arr - one_hot) ** 2, axis=1)))


def macro_f1(
    preds: npt.ArrayLike,
    labels: npt.ArrayLike,
    n_classes: int,
) -> float:
    """Macro-averaged F1 over ``n_classes``.

    Classes with no support are counted with F1=0 (standard sklearn macro
    behavior under zero_division=0). Returns a value in ``[0, 1]``.
    """
    preds_arr = np.asarray(preds, dtype=np.int64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if preds_arr.shape != labels_arr.shape:
        raise ValueError("preds and labels must have the same shape")
    if n_classes < 1:
        raise ValueError("n_classes must be >= 1")

    f1s: list[float] = []
    for c in range(n_classes):
        tp = int(((preds_arr == c) & (labels_arr == c)).sum())
        fp = int(((preds_arr == c) & (labels_arr != c)).sum())
        fn = int(((preds_arr != c) & (labels_arr == c)).sum())
        if tp + fp == 0 or tp + fn == 0:
            f1s.append(0.0)
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        if precision + recall == 0.0:
            f1s.append(0.0)
        else:
            f1s.append(2.0 * precision * recall / (precision + recall))
    return float(np.mean(f1s))


def per_class_recall(
    preds: npt.ArrayLike,
    labels: npt.ArrayLike,
    n_classes: int,
) -> tuple[FloatArray, IntArray]:
    """Per-class recall and support count.

    Returns ``(recall, support)``, each of length ``n_classes``. ``recall[c]``
    is ``TP / (TP + FN)`` for class ``c`` — the fraction of true-class-``c``
    samples the model recovered. Classes with zero support get
    ``recall[c] = 0.0`` and ``support[c] = 0``; the promotion gate enforces the
    recall floor only on adequately-supported classes so a class that is simply
    absent from the eval slice does not false-fail the gate.

    Macro-F1 can hide a single systematically-missed diagnostic when the common
    classes are strong; this surfaces it so a never-predicted fault blocks
    promotion. Cite ml-architecture.md §8 (no fault left undiagnosed) and §12.
    """
    preds_arr = np.asarray(preds, dtype=np.int64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if preds_arr.shape != labels_arr.shape:
        raise ValueError("preds and labels must have the same shape")
    if n_classes < 1:
        raise ValueError("n_classes must be >= 1")

    recall = np.zeros(n_classes, dtype=np.float64)
    support = np.zeros(n_classes, dtype=np.int64)
    for c in range(n_classes):
        is_c: BoolArray = labels_arr == c
        n_c = int(is_c.sum())
        support[c] = n_c
        if n_c == 0:
            continue
        tp = int((is_c & (preds_arr == c)).sum())
        recall[c] = tp / n_c
    return recall, support


def top_k_macro_f1(
    probs: npt.ArrayLike,
    labels: npt.ArrayLike,
    k: int,
    n_classes: int,
) -> float:
    """Macro-F1 where a sample counts as correct for its true class if its
    true class is in the top-k by predicted probability.

    Used for the top-3 macro-F1 ≥ 0.78 gate per ml-architecture.md §12.
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 2:
        raise ValueError("probs must be (N, C)")
    if k < 1 or k > probs_arr.shape[1]:
        raise ValueError("k must be in [1, n_classes]")

    top_k_idx = np.argsort(-probs_arr, axis=1)[:, :k]
    # For each sample, choose top-1 if true label is not in top-k, else
    # treat the predicted class as the true label so the per-class TP fires.
    in_top_k: BoolArray = np.array(
        [labels_arr[i] in top_k_idx[i] for i in range(probs_arr.shape[0])],
        dtype=np.bool_,
    )
    preds = top_k_idx[:, 0].copy()
    preds[in_top_k] = labels_arr[in_top_k]
    return macro_f1(preds, labels_arr, n_classes)


def conformal_coverage(
    prediction_sets: list[set[int]] | list[list[int]],
    labels: npt.ArrayLike,
) -> float:
    """Empirical coverage rate of conformal prediction sets.

    `prediction_sets[i]` is the set of class ids included in the conformal
    set for sample ``i``. Coverage is the fraction of samples whose true
    label is in their set. Target ≥ 0.88 (with a 2pt slack) for a 90%
    nominal level per ml-architecture.md §8.
    """
    labels_arr = np.asarray(labels, dtype=np.int64)
    if len(prediction_sets) != labels_arr.shape[0]:
        raise ValueError("prediction_sets and labels must agree on N")
    if labels_arr.shape[0] == 0:
        return 0.0
    covered = sum(
        int(int(lbl) in set(s)) for s, lbl in zip(prediction_sets, labels_arr, strict=True)
    )
    return float(covered) / float(labels_arr.shape[0])
