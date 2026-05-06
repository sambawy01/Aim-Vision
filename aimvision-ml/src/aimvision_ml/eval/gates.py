"""CI gate: ECE / macro-F1 / conformal-coverage / bias-axis thresholds.

Implements the promotion gate from docs/ml-architecture.md §13. The gate
runs on every candidate model and blocks the registry transition if any
threshold is breached.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from aimvision_ml.eval.metrics import (
    brier_score,
    conformal_coverage,
    expected_calibration_error,
    macro_f1,
    top_k_macro_f1,
)
from aimvision_ml.eval.stratify import DEFAULT_STRATIFICATION_AXES, Stratum, stratify
from aimvision_ml.schemas import GateResult


@dataclass(frozen=True)
class GateThresholds:
    """Promotion gate thresholds. Defaults track ml-architecture.md §12.

    `bias_axis_macro_f1_gap_max` is the maximum allowed spread of macro-F1
    across buckets within an axis. A 0.05-pt spread on any axis fails.
    """

    ece_max: float = 0.05
    top3_macro_f1_min: float = 0.78
    conformal_coverage_min: float = 0.88
    bias_axis_macro_f1_gap_max: float = 0.05


# Module-level default to avoid B008 (mutable default in function signature)
# while still keeping the gate thresholds visible to callers.
DEFAULT_GATE_THRESHOLDS = GateThresholds()


def evaluate(
    probs: npt.ArrayLike,
    labels: npt.ArrayLike,
    n_classes: int,
    *,
    prediction_sets: Sequence[set[int] | list[int]] | None = None,
    metadata: Sequence[dict[str, object]] | None = None,
    thresholds: GateThresholds = DEFAULT_GATE_THRESHOLDS,
) -> GateResult:
    """Evaluate a candidate model against the promotion gate.

    `probs` is (N, C) softmax probs. `labels` is (N,) integer class ids.
    `prediction_sets[i]` is the conformal set for sample i (optional; if
    omitted, conformal coverage is reported as 0.0 and the conformal gate
    is treated as failing). `metadata[i]` carries the axis fields for the
    bias audit; if omitted, the bias audit is skipped (no axes can fail).
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)

    ece = expected_calibration_error(probs_arr, labels_arr)
    brier = brier_score(probs_arr, labels_arr)
    preds = probs_arr.argmax(axis=1)
    overall_macro_f1 = macro_f1(preds, labels_arr, n_classes)
    top3 = top_k_macro_f1(probs_arr, labels_arr, k=min(3, n_classes), n_classes=n_classes)

    if prediction_sets is None:
        coverage = 0.0
    else:
        coverage = conformal_coverage([set(s) for s in prediction_sets], labels_arr)

    failed_axes: list[str] = []
    if metadata is not None:
        strata: list[Stratum] = stratify(metadata, axes=DEFAULT_STRATIFICATION_AXES)
        per_axis_f1: dict[str, list[float]] = {}
        for s in strata:
            if not s.sample_indices:
                continue
            idx = np.asarray(s.sample_indices, dtype=np.int64)
            f1 = macro_f1(preds[idx], labels_arr[idx], n_classes)
            per_axis_f1.setdefault(s.axis, []).append(f1)
        for axis, f1s in per_axis_f1.items():
            if len(f1s) < 2:
                continue
            gap = float(max(f1s) - min(f1s))
            if gap > thresholds.bias_axis_macro_f1_gap_max:
                failed_axes.append(f"{axis} (gap={gap:.3f})")

    passed = (
        ece <= thresholds.ece_max
        and top3 >= thresholds.top3_macro_f1_min
        and coverage >= thresholds.conformal_coverage_min
        and not failed_axes
    )

    notes_parts: list[str] = []
    if ece > thresholds.ece_max:
        notes_parts.append(f"ECE {ece:.3f} > {thresholds.ece_max}")
    if top3 < thresholds.top3_macro_f1_min:
        notes_parts.append(f"top3-macro-F1 {top3:.3f} < {thresholds.top3_macro_f1_min}")
    if coverage < thresholds.conformal_coverage_min:
        notes_parts.append(
            f"conformal-coverage {coverage:.3f} < {thresholds.conformal_coverage_min}"
        )
    if failed_axes:
        notes_parts.append("bias-axis fail: " + ", ".join(failed_axes))

    return GateResult(
        passed=passed,
        ece=ece,
        brier=brier,
        macro_f1=overall_macro_f1,
        top3_macro_f1=top3,
        conformal_coverage=coverage,
        failed_axes=failed_axes,
        notes="; ".join(notes_parts),
    )
