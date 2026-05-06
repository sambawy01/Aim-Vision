"""Multi-task loss with per-branch weights — torch import lazy.

Cite docs/ml-architecture.md §8 ("multi-task hierarchical, multi-label").
Each branch's BCE-with-logits is weighted independently per the per-branch
config in ``configs/diagnostic_head/base.yaml``. We import torch at call
time so the lightweight install path doesn't need it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import torch


def multitask_bce_loss(  # pragma: no cover  (heavy: requires torch)
    branch_logits: Mapping[str, torch.Tensor],
    branch_targets: Mapping[str, torch.Tensor],
    branch_weights: Mapping[str, float],
) -> torch.Tensor:
    """Sum of per-branch BCE-with-logits, weighted by branch importance.

    Each branch is multi-label inside the branch (atoms within a branch
    co-occur regularly per docs/diagnostic-taxonomy.md). The meta layer
    isn't trained here — meta is rule-based DAG ordering at inference.
    """
    import torch  # local import to keep the lightweight path lazy

    total: torch.Tensor | None = None
    bce: Any = torch.nn.functional.binary_cross_entropy_with_logits
    for name, logits in branch_logits.items():
        if name not in branch_targets:
            raise KeyError(f"missing target for branch {name!r}")
        w = float(branch_weights.get(name, 1.0))
        loss_b = bce(logits, branch_targets[name].to(logits.dtype))
        contrib = w * loss_b
        total = contrib if total is None else total + contrib
    if total is None:
        raise ValueError("branch_logits must be non-empty")
    return total
