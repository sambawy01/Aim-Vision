"""Active learning skeleton: BALD acquisition + coreset selection fallback.

Cite docs/ml-architecture.md §10 ("Don't burn Franco on labels"). BALD
uses ensemble disagreement; coreset is the fallback when ensemble
disagreement quality is low (early-training or post-distribution-shift).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class AcquisitionResult:
    indices: list[int]
    scores: list[float]
    method: str


def bald_scores(ensemble_probs: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Bayesian Active Learning by Disagreement scores.

    `ensemble_probs` is shape ``(M, N, C)`` — M ensemble members, N
    samples, C classes. BALD = H[E[p]] - E[H[p]]. Higher = more uncertain
    (predictive entropy net of expected entropy = epistemic uncertainty).
    """
    p = np.asarray(ensemble_probs, dtype=np.float64)
    if p.ndim != 3:
        raise ValueError(f"ensemble_probs must be (M, N, C); got {p.shape}")
    eps = 1e-12
    mean_p = p.mean(axis=0)  # (N, C)
    h_mean = -np.sum(mean_p * np.log(mean_p + eps), axis=1)  # (N,)
    h_each = -np.sum(p * np.log(p + eps), axis=2)  # (M, N)
    mean_h = h_each.mean(axis=0)  # (N,)
    out: npt.NDArray[np.float64] = h_mean - mean_h
    return out


def select_bald(
    ensemble_probs: npt.ArrayLike,
    budget: int,
) -> AcquisitionResult:
    """Pick top-`budget` indices by BALD score."""
    scores = bald_scores(ensemble_probs)
    if budget <= 0 or budget > scores.size:
        raise ValueError("budget must be in [1, N]")
    order = np.argsort(-scores)
    chosen = order[:budget].tolist()
    return AcquisitionResult(
        indices=[int(i) for i in chosen],
        scores=[float(scores[i]) for i in chosen],
        method="bald",
    )


def select_coreset(
    embeddings: npt.ArrayLike,
    budget: int,
    seed: int = 0,
) -> AcquisitionResult:
    """k-Center greedy coreset selection on a feature-embedding matrix.

    Doesn't depend on ensemble disagreement; safe fallback. Embeddings is
    shape ``(N, D)``. Picks budget points whose nearest-neighbor distance
    to the chosen set is maximized at each step.
    """
    emb = np.asarray(embeddings, dtype=np.float64)
    if emb.ndim != 2:
        raise ValueError(f"embeddings must be (N, D); got {emb.shape}")
    n = emb.shape[0]
    if budget <= 0 or budget > n:
        raise ValueError("budget must be in [1, N]")

    rng = np.random.default_rng(seed)
    first = int(rng.integers(0, n))
    chosen: list[int] = [first]
    min_dist = np.linalg.norm(emb - emb[first], axis=1)
    for _ in range(1, budget):
        next_idx = int(np.argmax(min_dist))
        chosen.append(next_idx)
        d_new = np.linalg.norm(emb - emb[next_idx], axis=1)
        min_dist = np.minimum(min_dist, d_new)
    return AcquisitionResult(
        indices=chosen,
        scores=[float(min_dist[i]) for i in chosen],
        method="coreset_kcenter",
    )
