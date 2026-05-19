"""Tests for `aimvision_ml.eval.diagnostic_eval`.

Synthetic-prediction harness — drives the multi-label gate with
deliberately-constructed probability + label matrices so each
threshold (per-atom ECE, per-branch macro-F1, overall macro-F1) can
be exercised in isolation. No real ONNX model required; that's the
production hook that lives in the registry's promotion path.
"""

from __future__ import annotations

import numpy as np
import pytest

from aimvision_ml.eval.diagnostic_eval import (
    AtomEvalResult,
    BranchEvalResult,
    DiagnosticGateThresholds,
    DiagnosticHeadEvalResult,
    binary_brier,
    binary_ece,
    binary_f1,
    evaluate_diagnostic_head,
)
from aimvision_ml.taxonomy import (
    BRANCH_OF,
    Branch,
    DiagnosticCategory,
    all_categories,
)


def _make_well_calibrated_probs(
    labels: np.ndarray, noise_scale: float = 0.05, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Build probabilities that are well calibrated against `labels`.

    For each labelled-positive row, draw probability ~Beta(8, 2) (mean
    ~0.8). For each labelled-negative row, draw ~Beta(2, 8) (mean
    ~0.2). Add small gaussian jitter then clip to [0.01, 0.99].
    """
    if rng is None:
        rng = np.random.default_rng(0)
    probs = np.zeros_like(labels, dtype=np.float64)
    positive_mask = labels.astype(bool)
    n_pos = int(positive_mask.sum())
    n_neg = int((~positive_mask).sum())
    probs[positive_mask] = rng.beta(8.0, 2.0, size=n_pos)
    probs[~positive_mask] = rng.beta(2.0, 8.0, size=n_neg)
    probs = probs + rng.normal(0.0, noise_scale, size=probs.shape)
    return np.clip(probs, 0.01, 0.99)


# ----------------------- binary primitive tests ----------------------


def test_binary_ece_zero_on_perfect_predictor() -> None:
    """If every probability matches its label exactly, ECE is 0."""
    labels = np.array([0, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
    probs = labels.astype(np.float64)
    assert binary_ece(probs, labels) == pytest.approx(0.0, abs=1e-12)


def test_binary_ece_nonzero_on_miscalibrated_predictor() -> None:
    """Constant prediction of 0.5 against a 0/1 split of true labels
    yields ECE = 0.5 - positive_rate (in absolute value).
    """
    labels = np.array([0, 0, 0, 1, 1, 1, 1, 1, 1, 1], dtype=np.int64)
    probs = np.full_like(labels, 0.5, dtype=np.float64)
    ece = binary_ece(probs, labels)
    # All 10 samples land in one bucket; mean conf 0.5, positive rate 0.7,
    # so ECE = |0.5 - 0.7| = 0.2.
    assert ece == pytest.approx(0.2, abs=1e-9)


def test_binary_brier_zero_on_perfect_predictor() -> None:
    labels = np.array([0, 1, 1, 0], dtype=np.int64)
    assert binary_brier(labels.astype(np.float64), labels) == 0.0


def test_binary_brier_quarter_on_constant_half_against_balanced() -> None:
    """Constant prediction of 0.5 against any binary label gives
    Brier = (0.5)^2 = 0.25 per sample."""
    labels = np.array([0, 1, 0, 1], dtype=np.int64)
    probs = np.full(4, 0.5)
    assert binary_brier(probs, labels) == pytest.approx(0.25)


def test_binary_f1_perfect_at_classifier_threshold() -> None:
    labels = np.array([0, 1, 1, 0, 1, 0], dtype=np.int64)
    probs = np.array([0.1, 0.9, 0.8, 0.2, 0.95, 0.05])
    assert binary_f1(probs, labels, threshold=0.5) == pytest.approx(1.0)


def test_binary_f1_zero_on_no_positive_predictions() -> None:
    """Every prediction is below threshold → no predicted positives →
    F1 = 0 by sklearn `zero_division=0` convention."""
    labels = np.array([0, 1, 1, 0], dtype=np.int64)
    probs = np.array([0.1, 0.2, 0.3, 0.05])
    assert binary_f1(probs, labels, threshold=0.5) == 0.0


def test_binary_primitives_validate_shapes() -> None:
    with pytest.raises(ValueError):
        binary_ece(np.zeros((2, 3)), np.zeros(2))
    with pytest.raises(ValueError):
        binary_brier(np.zeros(3), np.zeros(2))
    with pytest.raises(ValueError):
        binary_f1(np.zeros(3), np.zeros(3), threshold=1.5)


# ----------------------- evaluate_diagnostic_head tests --------------


def test_perfect_predictor_passes_gate() -> None:
    """A predictor that emits the binary label exactly should pass
    every threshold."""
    rng = np.random.default_rng(0)
    atoms = all_categories()
    n_samples = 200
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    # Slight nudge so predictions land strictly inside [0.01, 0.99] — keeps
    # the calibration metrics from degenerating to point-mass at the bin
    # edges (the implementation handles it, but a perfect 0/1 probe with
    # bin_edges at 0.0 and 1.0 is the degenerate case worth dodging).
    probs = labels.astype(np.float64) * 0.98 + 0.01
    result = evaluate_diagnostic_head(probs, labels)
    assert isinstance(result, DiagnosticHeadEvalResult)
    assert result.passed, f"perfect predictor unexpectedly failed: {result.failure_notes}"
    assert result.overall_macro_f1 == pytest.approx(1.0, abs=1e-9)
    assert result.overall_mean_ece < 0.05


def test_per_atom_failure_isolates_the_blocking_atom() -> None:
    """Construct a probability matrix that's perfect for every atom
    except HEAD_LIFT, which gets a constant 0.5 against a strongly
    positive label distribution → high ECE on that atom only.

    The gate must fail and must point at HEAD_LIFT (not at the entire
    branch and not at unrelated branches)."""
    rng = np.random.default_rng(1)
    atoms = all_categories()
    n_samples = 200
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    # Skew HEAD_LIFT's labels strongly positive to make 0.5 maximally
    # miscalibrated.
    head_lift_idx = atoms.index(DiagnosticCategory.HEAD_LIFT)
    labels[:, head_lift_idx] = 1
    probs = labels.astype(np.float64) * 0.98 + 0.01
    probs[:, head_lift_idx] = 0.5  # miscalibrated atom

    result = evaluate_diagnostic_head(probs, labels)
    assert not result.passed
    assert any(
        "head_lift" in note for note in result.failure_notes
    ), f"expected head_lift in failure_notes; got {result.failure_notes}"
    # The HEAD_EYE branch should fail too (mean ECE pulled up by the
    # one atom), but other branches should not.
    assert any(
        "head_eye" in note and ("mean ECE" in note or "macro-F1" in note)
        for note in result.failure_notes
    )
    # Mount/Stance, Swing/Lead, Follow-through, Meta atoms remain
    # well-calibrated, so the failure list shouldn't mention them.
    for branch_value in ("mount_stance", "swing_lead", "follow_through", "meta"):
        assert not any(
            f"branch {branch_value}" in note for note in result.failure_notes
        ), f"{branch_value} should not appear in failures: {result.failure_notes}"


def test_branch_macro_f1_floor_blocks_under_performing_branch() -> None:
    """If a whole branch's predictions are noise (~0.5 ± jitter) against
    a roughly balanced label set, the branch's macro-F1 drops below
    the 0.55 floor and the gate fails on the branch line specifically.
    """
    rng = np.random.default_rng(2)
    atoms = all_categories()
    n_samples = 300
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    probs = labels.astype(np.float64) * 0.98 + 0.01

    # Wipe SWING_LEAD predictions to noise.
    swing_atoms = [a for a in atoms if BRANCH_OF[a] == Branch.SWING_LEAD]
    for atom in swing_atoms:
        col = atoms.index(atom)
        probs[:, col] = rng.beta(2.0, 2.0, size=n_samples)

    result = evaluate_diagnostic_head(probs, labels)
    assert not result.passed
    assert any("branch swing_lead" in note and "macro-F1" in note for note in result.failure_notes)


def test_branch_aggregation_groups_atoms_correctly() -> None:
    """`BranchEvalResult.atom_results` must contain exactly the atoms
    that belong to that branch — no leakage across branches.
    Sanity check against the taxonomy's BRANCH_OF mapping."""
    rng = np.random.default_rng(3)
    atoms = all_categories()
    n_samples = 100
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    probs = _make_well_calibrated_probs(labels, rng=rng)
    result = evaluate_diagnostic_head(probs, labels)

    for branch, branch_result in result.branch_results.items():
        for ar in branch_result.atom_results:
            assert ar.branch == branch
            assert BRANCH_OF[ar.atom] == branch
        # Result is a frozen dataclass → tuple field; ensure we have
        # the right *count* of atoms per branch.
        expected_count = sum(1 for a in atoms if BRANCH_OF[a] == branch)
        assert len(branch_result.atom_results) == expected_count


def test_threshold_override_changes_f1_at_atom_level() -> None:
    """Raising an atom's threshold from the default to 0.99 will
    suppress almost all positive predictions, dropping its F1 to 0."""
    rng = np.random.default_rng(4)
    atoms = all_categories()
    n_samples = 100
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    # Build a well-correlated probe at p~0.7 for positives, p~0.3 for negatives.
    probs = np.where(labels == 1, 0.70, 0.30).astype(np.float64)

    # Default threshold (0.55 for HEAD_LIFT) → F1 high.
    base_result = evaluate_diagnostic_head(probs, labels)
    head_lift_idx = next(
        i
        for i, ar in enumerate(base_result.branch_results[Branch.HEAD_EYE].atom_results)
        if ar.atom == DiagnosticCategory.HEAD_LIFT
    )
    base_f1 = base_result.branch_results[Branch.HEAD_EYE].atom_results[head_lift_idx].f1
    assert base_f1 > 0.3, f"baseline F1 unexpectedly low: {base_f1}"

    # Override HEAD_LIFT's threshold to 0.99 — all predictions fall
    # below, no positives predicted, F1 collapses to 0.
    overridden = evaluate_diagnostic_head(
        probs,
        labels,
        thresholds_per_atom={DiagnosticCategory.HEAD_LIFT: 0.99},
    )
    head_lift_result = next(
        ar
        for ar in overridden.branch_results[Branch.HEAD_EYE].atom_results
        if ar.atom == DiagnosticCategory.HEAD_LIFT
    )
    assert head_lift_result.f1 == 0.0


def test_evaluate_validates_inputs() -> None:
    atoms = all_categories()
    with pytest.raises(ValueError):
        # Wrong column count.
        evaluate_diagnostic_head(np.zeros((10, 3)), np.zeros((10, 3), dtype=np.int64))
    with pytest.raises(ValueError):
        # Empty batch.
        evaluate_diagnostic_head(
            np.zeros((0, len(atoms))), np.zeros((0, len(atoms)), dtype=np.int64)
        )
    with pytest.raises(ValueError):
        # Probs out of [0, 1] (caller probably passed logits).
        bad_probs = np.full((5, len(atoms)), 3.5)
        bad_labels = np.zeros((5, len(atoms)), dtype=np.int64)
        evaluate_diagnostic_head(bad_probs, bad_labels)


def test_result_dataclasses_carry_per_atom_detail() -> None:
    """The returned structures must let a caller inspect each atom's
    individual ECE / F1 — this is what the registry uses to point at
    the failing atom in the promotion-blocked message."""
    rng = np.random.default_rng(5)
    atoms = all_categories()
    n_samples = 50
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    probs = _make_well_calibrated_probs(labels, rng=rng)
    result = evaluate_diagnostic_head(probs, labels)

    for branch_result in result.branch_results.values():
        assert isinstance(branch_result, BranchEvalResult)
        for ar in branch_result.atom_results:
            assert isinstance(ar, AtomEvalResult)
            assert 0.0 <= ar.f1 <= 1.0
            assert ar.ece >= 0.0
            assert ar.brier >= 0.0
            assert ar.support == int(np.sum(labels[:, atoms.index(ar.atom)] == 1))


def test_custom_gate_thresholds_change_pass_fail() -> None:
    """A run that fails the default gate should pass when the threshold
    is loosened, and vice versa."""
    rng = np.random.default_rng(6)
    atoms = all_categories()
    n_samples = 200
    labels = rng.integers(0, 2, size=(n_samples, len(atoms))).astype(np.int64)
    # Modestly miscalibrated: positives at 0.75 (above every default
    # abstention threshold so the F1 derivation isn't suppressed) and
    # negatives at 0.20. Calibration error sits in the 0.2 range —
    # fine for "loose threshold passes, strict threshold fails."
    probs = np.where(labels == 1, 0.75, 0.20).astype(np.float64)

    strict = evaluate_diagnostic_head(
        probs,
        labels,
        gate_thresholds=DiagnosticGateThresholds(
            per_branch_macro_f1_min=0.95,
        ),
    )
    assert not strict.passed

    loose = evaluate_diagnostic_head(
        probs,
        labels,
        gate_thresholds=DiagnosticGateThresholds(
            per_atom_ece_max=0.5,
            per_branch_mean_ece_max=0.5,
            per_branch_macro_f1_min=0.1,
            overall_macro_f1_min=0.1,
        ),
    )
    assert loose.passed
