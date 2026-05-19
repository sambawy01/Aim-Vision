"""Diagnostic-head training + ONNX export (ml-architecture.md §8).

This is the *training/export* half of the diagnostic-head pipeline;
the inference half is `aimvision_ml.inference.diagnostic_onnx`. The
two share the taxonomy atom order (`all_categories()`) as the single
source of truth for the 15 multi-label output columns.

# Torch-gated, ships no weights

torch is imported lazily and lives in the `train` extra, so the
lightweight CI install never pulls it. Critically, **no trained
weights are committed**: the head must be trained on real Egypt
range data on a GPU (Sprint 9). This module provides the runnable
pipeline (model def → train loop → ONNX export) that produces a
model artifact when real data + compute exist. The caller supplies
the training data; we deliberately do NOT bake in synthetic data,
so nobody can mistake a toy artifact for a coaching-grade model.

# Output contract

The exported ONNX graph emits **sigmoid probabilities** (not
logits), one column per atom in `all_categories()` order, so
`DiagnosticOnnxModel.predict` can consume it directly. Multi-label:
atoms co-occur, hence per-atom sigmoid rather than a softmax.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aimvision_ml.taxonomy import all_categories

if TYPE_CHECKING:
    import numpy as np

NUM_ATOMS = len(all_categories())


def _require_torch() -> Any:
    try:
        import torch
    except ModuleNotFoundError as e:  # pragma: no cover - exercised only w/o torch
        raise ModuleNotFoundError(
            "diagnostic_export requires torch — install with `uv sync --extra train`."
        ) from e
    return torch


def build_head(feature_dim: int, hidden: int = 128) -> Any:
    """A minimal multi-label diagnostic head: feature_dim → hidden →
    NUM_ATOMS, with a trailing Sigmoid so the exported graph emits
    probabilities directly. The eventual design (ml-architecture.md
    §8) is per-branch experts with temperature scaling; that can
    replace the internals without changing the ONNX I/O contract
    (feature_dim in, NUM_ATOMS probabilities out).

    Built as an `nn.Sequential` rather than a custom `nn.Module`
    subclass so the lazily-imported (untyped) torch doesn't trip the
    type checker.
    """
    torch = _require_torch()
    nn = torch.nn
    return nn.Sequential(
        nn.Linear(feature_dim, hidden),
        nn.ReLU(),
        nn.Linear(hidden, NUM_ATOMS),
        nn.Sigmoid(),
    )


def train_head(
    model: Any,
    features: np.ndarray,
    labels: np.ndarray,
    *,
    epochs: int = 50,
    lr: float = 1e-3,
) -> Any:
    """Train the head on caller-supplied data with BCE loss.

    `features` is (N, feature_dim) float; `labels` is (N, NUM_ATOMS)
    in {0,1} (multi-label). Returns the trained model. No data is
    fabricated here — real labels come from Franco's annotations.
    """
    torch = _require_torch()
    import numpy as np

    x = torch.as_tensor(np.asarray(features), dtype=torch.float32)
    y = torch.as_tensor(np.asarray(labels), dtype=torch.float32)
    if y.shape[1] != NUM_ATOMS:
        raise ValueError(f"labels must have {NUM_ATOMS} columns, got {y.shape[1]}")

    # BCELoss (model already applies sigmoid). For training stability a
    # logits+BCEWithLogits split would be marginally better, but keeping
    # the sigmoid in-graph means the export needs no extra node.
    loss_fn = torch.nn.BCELoss()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(model(x), y)
        loss.backward()
        opt.step()
    return model


def export_to_onnx(model: Any, feature_dim: int, path: str | Path) -> Path:
    """Export a trained head to ONNX with a dynamic batch axis.

    The output is named `probabilities`; input `features`. Matches
    `DiagnosticOnnxModel`'s single-input / single-output contract.
    """
    torch = _require_torch()

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    dummy = torch.zeros((1, feature_dim), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["features"],
        output_names=["probabilities"],
        dynamic_axes={"features": {0: "batch"}, "probabilities": {0: "batch"}},
        opset_version=17,
    )
    return out_path
