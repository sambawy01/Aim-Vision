"""Multi-label diagnostic-head evaluation gate.

The single-task gate in `eval/gates.py` takes one-label-per-shot
predictions and runs ECE + macro-F1 + conformal-coverage + bias-axis
thresholds against them. That's the right shape for a flat
N-of-many classifier.

The diagnostic head from `ml-architecture.md` §8 is a different
animal:

  * Multi-label — each shot can simultaneously carry multiple atoms
    (e.g. `HEAD_LIFT` + `SHORT_FOLLOW_THROUGH` co-occur on the same
    swing).
  * Multi-task / hierarchical — atoms are grouped under five branch
    experts (Head/Eye, Mount/Stance, Swing/Lead, Follow-through,
    Meta); each branch should be calibrated and discriminating on its
    own, not just in aggregate.
  * Per-atom abstention — each atom carries its own confidence
    threshold from `DEFAULT_ABSTENTION_THRESHOLDS`. The gate must
    respect those thresholds when deriving binary predictions.

This module ships the eval-gate logic specific to that shape:

  * `binary_ece` / `binary_brier` — calibration metrics for a single
    binary classifier (each atom is one). `metrics.py`'s versions
    assume (N, C) softmax shape, so they don't fit per-atom.
  * `AtomEvalResult` / `BranchEvalResult` / `DiagnosticHeadEvalResult`
    — the result schema, with per-atom detail so a failure surface
    points at the exact atom that's blocking promotion.
  * `evaluate_diagnostic_head` — the top-level gate; takes (N, K)
    probability + (N, K) binary label matrices indexed by
    `taxonomy.all_categories()` order and returns a structured
    result.

This is the gate the registry will run on every candidate diagnostic
head before promotion. CI runs the same gate on synthetic data so the
metric definitions don't drift before the real ONNX model arrives.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from aimvision_ml.eval.stratify import DEFAULT_STRATIFICATION_AXES, stratify
from aimvision_ml.taxonomy import (
    BRANCH_OF,
    DEFAULT_ABSTENTION_THRESHOLDS,
    Branch,
    DiagnosticCategory,
    all_categories,
    categories_for,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


def binary_ece(probs: npt.ArrayLike, labels: npt.ArrayLike, n_bins: int = 15) -> float:
    """Expected Calibration Error for a single binary classifier.

    `probs` is a 1-D array of probabilities of the positive class.
    `labels` is a 1-D 0/1 array. Buckets are by predicted probability;
    each bucket's contribution is the gap between mean predicted
    probability and observed positive rate, weighted by bucket size.

    Returns a non-negative float in `[0, 1]`. Lower is better.
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 1:
        raise ValueError(f"probs must be 1-D; got shape {probs_arr.shape}")
    if labels_arr.shape != probs_arr.shape:
        raise ValueError("probs and labels must have the same shape")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    if probs_arr.size == 0:
        return 0.0

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = float(probs_arr.size)
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask: BoolArray = (probs_arr >= lo) & (probs_arr <= hi)
        else:
            mask = (probs_arr >= lo) & (probs_arr < hi)
        bucket_n = int(mask.sum())
        if bucket_n == 0:
            continue
        mean_prob = float(probs_arr[mask].mean())
        positive_rate = float(labels_arr[mask].mean())
        ece += (bucket_n / n) * abs(mean_prob - positive_rate)
    return float(ece)


def binary_brier(probs: npt.ArrayLike, labels: npt.ArrayLike) -> float:
    """Brier score for a single binary classifier: `mean((p - y)^2)`."""
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 1:
        raise ValueError(f"probs must be 1-D; got {probs_arr.shape}")
    if labels_arr.shape != probs_arr.shape:
        raise ValueError("probs and labels must have the same shape")
    if probs_arr.size == 0:
        return 0.0
    return float(np.mean((probs_arr - labels_arr.astype(np.float64)) ** 2))


def binary_f1(probs: npt.ArrayLike, labels: npt.ArrayLike, threshold: float) -> float:
    """F1 score for a single binary classifier at a given threshold.

    Returns 0.0 if there are no positive predictions OR no positive
    labels — matches the standard sklearn `zero_division=0` behavior.
    """
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    if probs_arr.ndim != 1 or labels_arr.ndim != 1:
        raise ValueError("probs and labels must both be 1-D")
    if probs_arr.shape != labels_arr.shape:
        raise ValueError("probs and labels must have the same shape")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1]; got {threshold}")

    preds = (probs_arr >= threshold).astype(np.int64)
    tp = int(np.sum((preds == 1) & (labels_arr == 1)))
    fp = int(np.sum((preds == 1) & (labels_arr == 0)))
    fn = int(np.sum((preds == 0) & (labels_arr == 1)))
    if tp + fp == 0 or tp + fn == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    if precision + recall == 0.0:
        return 0.0
    return float(2.0 * precision * recall / (precision + recall))


@dataclass(frozen=True)
class AtomEvalResult:
    """Per-atom diagnostic-head metrics.

    `support` is the count of true positives (samples where this atom
    is labelled). When support is 0 the F1 is 0 by definition and the
    calibration metrics still report correctly but the caller should
    treat low-support atoms with caution.
    """

    atom: DiagnosticCategory
    branch: Branch
    threshold: float
    f1: float
    ece: float
    brier: float
    positive_rate_predicted: float
    positive_rate_true: float
    support: int


@dataclass(frozen=True)
class BranchEvalResult:
    """Aggregated metrics for one branch (Head/Eye, Mount/Stance, etc.)."""

    branch: Branch
    macro_f1: float
    mean_ece: float
    mean_brier: float
    atom_results: tuple[AtomEvalResult, ...]


@dataclass(frozen=True)
class DiagnosticGateThresholds:
    """Promotion-gate thresholds for the multi-label diagnostic head.

    These are looser than the single-task `GateThresholds` in
    `gates.py` because multi-label per-atom calibration is naturally
    noisier (each atom's binary problem has fewer positive samples
    than a flat N-of-many setup). They track
    `ml-architecture.md` §13.
    """

    per_atom_ece_max: float = 0.10
    """Per-atom binary ECE; an atom failing this fails the gate."""
    per_branch_mean_ece_max: float = 0.07
    """Mean-of-atoms ECE per branch; gate fails if any branch exceeds it."""
    per_branch_macro_f1_min: float = 0.55
    """Macro-F1 across the branch's atoms; gate fails if any branch
    drops below this floor."""
    overall_macro_f1_min: float = 0.55
    """Macro-F1 across all atoms; gate fails if total drops below this."""
    bias_axis_macro_f1_gap_max: float = 0.05
    """Max permitted spread of macro-F1 across buckets within a single
    bias axis (station, lighting, body_type, skin_tone, ...). A gap > this
    value fails the gate per ml-architecture.md §12. Matches the
    single-task gate's `GateThresholds.bias_axis_macro_f1_gap_max`."""
    bias_axis_min_bucket_size: int = 30
    """Below this sample count, a bucket is excluded from the axis-gap
    audit — a single-digit bucket gives noisy F1 estimates that would
    fail the gate spuriously. The training-data sampler is expected to
    surface this exclusion in the eval report."""


DEFAULT_DIAGNOSTIC_THRESHOLDS = DiagnosticGateThresholds()


@dataclass(frozen=True)
class DiagnosticHeadEvalResult:
    """Top-level multi-label gate result.

    `failure_notes` lists exactly which atom/branch/axis fails, so the
    gate's "blocked promotion" message points at the specific metric
    that's off. Empty iff `passed` is True. `failed_axes` is the
    subset of failure_notes attributable to the bias-axis audit; it's
    surfaced separately because mitigating a bias gap usually means
    rebalancing the training set, not retuning the model.
    """

    overall_macro_f1: float
    overall_mean_ece: float
    branch_results: dict[Branch, BranchEvalResult] = field(default_factory=dict)
    passed: bool = False
    failure_notes: tuple[str, ...] = field(default_factory=tuple)
    failed_axes: tuple[str, ...] = field(default_factory=tuple)


def _validate_inputs(probs: FloatArray, labels: IntArray, atoms: list[DiagnosticCategory]) -> None:
    if probs.ndim != 2 or labels.ndim != 2:
        raise ValueError(f"probs and labels must be 2-D; got {probs.shape}, {labels.shape}")
    if probs.shape != labels.shape:
        raise ValueError(f"probs and labels shape mismatch: {probs.shape} vs {labels.shape}")
    if probs.shape[1] != len(atoms):
        raise ValueError(
            f"probs has {probs.shape[1]} columns; expected {len(atoms)} "
            f"(one per atom in taxonomy.all_categories())"
        )
    if probs.shape[0] == 0:
        raise ValueError("need at least one shot to evaluate")
    # We don't enforce probs in [0, 1] strictly because callers may
    # pass logits in some workflows; the metrics handle it gracefully
    # but flag obviously wrong inputs.
    if probs.min() < -1e-9 or probs.max() > 1.0 + 1e-9:
        raise ValueError(
            f"probs out of [0, 1]: min={probs.min()}, max={probs.max()} "
            f"— pass calibrated probabilities, not logits"
        )


def evaluate_diagnostic_head(
    probs: npt.ArrayLike,
    labels: npt.ArrayLike,
    *,
    atoms: list[DiagnosticCategory] | None = None,
    thresholds_per_atom: dict[DiagnosticCategory, float] | None = None,
    gate_thresholds: DiagnosticGateThresholds = DEFAULT_DIAGNOSTIC_THRESHOLDS,
    metadata: Sequence[dict[str, object]] | None = None,
) -> DiagnosticHeadEvalResult:
    """Run the diagnostic-head promotion gate.

    `probs` is `(N, K)` calibrated probabilities, columns indexed in the
    canonical order from `taxonomy.all_categories()` (override via
    `atoms` if the caller maintains a different index). `labels` is
    `(N, K)` binary; element `[n, k]` is 1 iff shot n carries atom k.

    `thresholds_per_atom` overrides the default
    `DEFAULT_ABSTENTION_THRESHOLDS` for the F1 derivation (the F1 score
    depends on what threshold the prober uses). If omitted, the taxonomy
    defaults are used.

    `metadata`, when supplied as a length-N sequence of dicts (one per
    shot), enables the bias-axis audit: for each axis in
    `DEFAULT_STRATIFICATION_AXES` (station, lighting, body_type, ...)
    the gate computes the macro-F1 spread across buckets and fails if
    the spread exceeds `bias_axis_macro_f1_gap_max`. Omitting metadata
    skips the audit (the gate is silent about bias, not vacuously
    passing) — pass it whenever you have it.
    """
    atoms_list = atoms or all_categories()
    probs_arr = np.asarray(probs, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)
    _validate_inputs(probs_arr, labels_arr, atoms_list)

    per_atom_thresholds = dict(DEFAULT_ABSTENTION_THRESHOLDS)
    if thresholds_per_atom:
        per_atom_thresholds.update(thresholds_per_atom)

    # Compute per-atom metrics.
    atom_results: dict[DiagnosticCategory, AtomEvalResult] = {}
    for k, atom in enumerate(atoms_list):
        col_probs = probs_arr[:, k]
        col_labels = labels_arr[:, k]
        thr = per_atom_thresholds.get(atom, 0.5)
        ece = binary_ece(col_probs, col_labels)
        brier = binary_brier(col_probs, col_labels)
        f1 = binary_f1(col_probs, col_labels, thr)
        preds_positive = float(np.mean(col_probs >= thr))
        true_positive = float(np.mean(col_labels == 1))
        support = int(np.sum(col_labels == 1))
        atom_results[atom] = AtomEvalResult(
            atom=atom,
            branch=BRANCH_OF[atom],
            threshold=thr,
            f1=f1,
            ece=ece,
            brier=brier,
            positive_rate_predicted=preds_positive,
            positive_rate_true=true_positive,
            support=support,
        )

    # Group into branches.
    branch_results: dict[Branch, BranchEvalResult] = {}
    for branch in Branch:
        branch_atoms = categories_for(branch)
        branch_atom_results = tuple(atom_results[a] for a in branch_atoms if a in atom_results)
        if not branch_atom_results:
            continue
        macro_f1 = float(np.mean([r.f1 for r in branch_atom_results]))
        mean_ece = float(np.mean([r.ece for r in branch_atom_results]))
        mean_brier = float(np.mean([r.brier for r in branch_atom_results]))
        branch_results[branch] = BranchEvalResult(
            branch=branch,
            macro_f1=macro_f1,
            mean_ece=mean_ece,
            mean_brier=mean_brier,
            atom_results=branch_atom_results,
        )

    overall_macro_f1 = float(np.mean([r.f1 for r in atom_results.values()]))
    overall_mean_ece = float(np.mean([r.ece for r in atom_results.values()]))

    # Apply the gate.
    failure_notes: list[str] = []
    for atom, ar in atom_results.items():
        if ar.ece > gate_thresholds.per_atom_ece_max:
            failure_notes.append(
                f"atom {atom.value}: ECE {ar.ece:.3f} > {gate_thresholds.per_atom_ece_max}"
            )
    for branch, br in branch_results.items():
        if br.mean_ece > gate_thresholds.per_branch_mean_ece_max:
            failure_notes.append(
                f"branch {branch.value}: mean ECE {br.mean_ece:.3f} > "
                f"{gate_thresholds.per_branch_mean_ece_max}"
            )
        if br.macro_f1 < gate_thresholds.per_branch_macro_f1_min:
            failure_notes.append(
                f"branch {branch.value}: macro-F1 {br.macro_f1:.3f} < "
                f"{gate_thresholds.per_branch_macro_f1_min}"
            )
    if overall_macro_f1 < gate_thresholds.overall_macro_f1_min:
        failure_notes.append(
            f"overall macro-F1 {overall_macro_f1:.3f} < {gate_thresholds.overall_macro_f1_min}"
        )

    # Bias-axis audit. The macro-F1 per bucket is the mean across all
    # atoms — same definition as `overall_macro_f1` but restricted to
    # the bucket's sample indices. We surface the failed axes through
    # both `failure_notes` (for the human-readable failure list) and
    # the dedicated `failed_axes` tuple so the registry can route a
    # bias-gap failure to the data team, not the model team.
    failed_axes: list[str] = []
    if metadata is not None:
        if len(metadata) != probs_arr.shape[0]:
            raise ValueError(
                f"metadata length {len(metadata)} must match probs length {probs_arr.shape[0]}"
            )
        strata = stratify(metadata, axes=DEFAULT_STRATIFICATION_AXES)
        per_axis_macro_f1: dict[str, list[float]] = {}
        for s in strata:
            if len(s.sample_indices) < gate_thresholds.bias_axis_min_bucket_size:
                continue
            idx = np.asarray(s.sample_indices, dtype=np.int64)
            sub_probs = probs_arr[idx]
            sub_labels = labels_arr[idx]
            f1s = [
                binary_f1(
                    sub_probs[:, k],
                    sub_labels[:, k],
                    per_atom_thresholds.get(atom, 0.5),
                )
                for k, atom in enumerate(atoms_list)
            ]
            bucket_macro_f1 = float(np.mean(f1s))
            per_axis_macro_f1.setdefault(s.axis, []).append(bucket_macro_f1)
        for axis, f1s in per_axis_macro_f1.items():
            # Need at least 2 buckets above the size floor to compute a
            # gap. A single bucket means the axis is degenerate on this
            # eval set — the data team should know, but we don't fail.
            if len(f1s) < 2:
                continue
            gap = float(max(f1s) - min(f1s))
            if gap > gate_thresholds.bias_axis_macro_f1_gap_max:
                note = f"{axis} (gap={gap:.3f})"
                failed_axes.append(note)
                failure_notes.append(f"bias axis {note}")

    return DiagnosticHeadEvalResult(
        overall_macro_f1=overall_macro_f1,
        overall_mean_ece=overall_mean_ece,
        branch_results=branch_results,
        passed=not failure_notes,
        failure_notes=tuple(failure_notes),
        failed_axes=tuple(failed_axes),
    )


__all__ = [
    "DEFAULT_DIAGNOSTIC_THRESHOLDS",
    "AtomEvalResult",
    "BranchEvalResult",
    "DiagnosticGateThresholds",
    "DiagnosticHeadEvalResult",
    "binary_brier",
    "binary_ece",
    "binary_f1",
    "evaluate_diagnostic_head",
]
