"""Multi-task hierarchical diagnostic-head wrapper interface.

Cite docs/ml-architecture.md §8 — four branch experts (Head/Eye,
Mount/Stance, Swing/Lead, Follow-through) plus a Meta-classifier emit
calibrated probabilities per atom. Multi-label by construction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import numpy as np
import numpy.typing as npt

from aimvision_ml.schemas import AtomPrediction, ShotFeatureVector, ShotPrediction
from aimvision_ml.taxonomy import (
    BRANCH_OF,
    DEFAULT_ABSTENTION_THRESHOLDS,
    Branch,
    DiagnosticCategory,
    all_categories,
)


class DiagnosticHead(Protocol):
    """ONNX-runtime-backed wrapper protocol."""

    def infer(self, features: ShotFeatureVector) -> ShotPrediction: ...


class StubDiagnosticHead:
    """Deterministic stub for unit tests and pipeline wiring.

    Emits a uniform-low probability per atom; abstention fires on every
    shot. The real wrapper loads an ONNX model from the registry.
    """

    def __init__(self, model_version: str = "stub-v0", taxonomy_version: str = "0.9-draft") -> None:
        self.model_version = model_version
        self.taxonomy_version = taxonomy_version

    def infer(self, features: ShotFeatureVector) -> ShotPrediction:
        cats = all_categories()
        probs = np.full(len(cats), 0.10, dtype=np.float32)
        atoms = [
            AtomPrediction(category=c, probability=float(p), in_conformal_set=False)
            for c, p in zip(cats, probs, strict=True)
        ]
        return ShotPrediction(
            shot_id=features.shot_id,
            session_id=features.session_id,
            atoms=atoms,
            primary=None,
            abstained=True,
            model_version=self.model_version,
            taxonomy_version=self.taxonomy_version,
            predicted_at=datetime.now(UTC),
        )


# DAG ordering for compound-fault attribution per docs/diagnostic-taxonomy.md
# §Meta `multi_factor`. Earlier-in-chain branches surface as the primary
# cause when multiple branches fire above threshold on the same shot.
_BRANCH_DAG_ORDER: tuple[Branch, ...] = (
    Branch.MOUNT_STANCE,  # stance → mount
    Branch.HEAD_EYE,
    Branch.SWING_LEAD,  # → swing → break
    Branch.FOLLOW_THROUGH,
)


def select_primary(
    probabilities: dict[DiagnosticCategory, float],
    thresholds: dict[DiagnosticCategory, float] | None = None,
) -> DiagnosticCategory | None:
    """Apply per-class thresholds and DAG-prior ordering to pick the
    primary cause for a shot.

    Returns ``None`` if no atom clears its threshold (the abstention case).
    Cite docs/diagnostic-taxonomy.md §Meta and ml-architecture.md §8.
    """
    th = thresholds or DEFAULT_ABSTENTION_THRESHOLDS
    above: list[tuple[DiagnosticCategory, float]] = [
        (c, p) for c, p in probabilities.items() if p >= th.get(c, 1.0)
    ]
    if not above:
        return None
    # Sort by DAG-branch order, then by probability desc within branch.
    branch_rank = {b: i for i, b in enumerate(_BRANCH_DAG_ORDER)}
    above.sort(
        key=lambda cp: (
            branch_rank.get(BRANCH_OF.get(cp[0], Branch.META), len(_BRANCH_DAG_ORDER)),
            -cp[1],
        )
    )
    return above[0][0]


def softmax(logits: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Numerically-stable softmax over the last axis."""
    arr = np.asarray(logits, dtype=np.float64)
    shifted = arr - arr.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    out: npt.NDArray[np.float64] = exp / exp.sum(axis=-1, keepdims=True)
    return out
