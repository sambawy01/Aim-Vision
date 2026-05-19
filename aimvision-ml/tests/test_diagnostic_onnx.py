"""Tests for the diagnostic-head ONNX inference plumbing.

The CI-runnable tests author a tiny ONNX graph with `onnx.helper`
(no torch needed) and drive it through `DiagnosticOnnxModel`. A
separate torch-gated test exercises the real
`training.diagnostic_export` train→export→load roundtrip and skips
when torch isn't installed (the default CI image).

No model weights are committed to the repo — these tests build
throwaway graphs in tmp_path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from aimvision_ml.inference.diagnostic_onnx import (
    ATOM_ORDER,
    NUM_ATOMS,
    DiagnosticOnnxModel,
)
from aimvision_ml.taxonomy import DiagnosticCategory

_HAS_ONNX = importlib.util.find_spec("onnx") is not None
_HAS_ORT = importlib.util.find_spec("onnxruntime") is not None
_HAS_TORCH = importlib.util.find_spec("torch") is not None

onnx_required = pytest.mark.skipif(
    not (_HAS_ONNX and _HAS_ORT),
    reason="needs the `infer` extra (onnx + onnxruntime)",
)


def _author_sigmoid_model(path: Path, feature_dim: int, num_atoms: int = NUM_ATOMS) -> None:
    """Hand-build a minimal ONNX graph: (batch, F) -> MatMul(W) ->
    Add(b) -> Sigmoid -> (batch, num_atoms). Deterministic small
    weights; this is plumbing scaffolding, not a trained model."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = (rng.standard_normal((feature_dim, num_atoms)) * 0.1).astype(np.float32)
    b = np.zeros((num_atoms,), dtype=np.float32)

    inp = helper.make_tensor_value_info("features", TensorProto.FLOAT, ["batch", feature_dim])
    out = helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, ["batch", num_atoms])
    w_init = numpy_helper.from_array(w, name="W")
    b_init = numpy_helper.from_array(b, name="B")

    matmul = helper.make_node("MatMul", ["features", "W"], ["xw"])
    add = helper.make_node("Add", ["xw", "B"], ["logits"])
    sig = helper.make_node("Sigmoid", ["logits"], ["probabilities"])

    graph = helper.make_graph(
        [matmul, add, sig],
        "diagnostic_head_stub",
        [inp],
        [out],
        initializer=[w_init, b_init],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 17)])
    model.ir_version = 10
    onnx.checker.check_model(model)
    onnx.save(model, str(path))


@onnx_required
def test_load_or_none_returns_none_for_missing(tmp_path: Path) -> None:
    """The production gate: no model file → None (no fabricated preds)."""
    assert DiagnosticOnnxModel.load_or_none(None) is None
    assert DiagnosticOnnxModel.load_or_none(tmp_path / "nope.onnx") is None


@onnx_required
def test_load_raises_for_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DiagnosticOnnxModel.load(tmp_path / "missing.onnx")


@onnx_required
def test_predict_returns_probabilities_per_atom(tmp_path: Path) -> None:
    model_path = tmp_path / "head.onnx"
    _author_sigmoid_model(model_path, feature_dim=8)
    model = DiagnosticOnnxModel.load(model_path)
    assert model.feature_dim == 8

    out = model.predict(np.zeros(8, dtype=np.float32))
    # One probability per atom, keyed by the canonical taxonomy.
    assert set(out.keys()) == set(ATOM_ORDER)
    assert len(out) == NUM_ATOMS
    for v in out.values():
        assert 0.0 <= v <= 1.0
    # Zero input + zero bias → sigmoid(0) = 0.5 for every atom.
    assert out[DiagnosticCategory.HEAD_LIFT] == pytest.approx(0.5, abs=1e-5)


@onnx_required
def test_predict_batch_shape(tmp_path: Path) -> None:
    model_path = tmp_path / "head.onnx"
    _author_sigmoid_model(model_path, feature_dim=6)
    model = DiagnosticOnnxModel.load(model_path)
    batch = np.zeros((4, 6), dtype=np.float32)
    probs = model.predict_batch(batch)
    assert probs.shape == (4, NUM_ATOMS)


@onnx_required
def test_predict_rejects_wrong_feature_width(tmp_path: Path) -> None:
    model_path = tmp_path / "head.onnx"
    _author_sigmoid_model(model_path, feature_dim=8)
    model = DiagnosticOnnxModel.load(model_path)
    with pytest.raises(ValueError, match="expects 8 features"):
        model.predict(np.zeros(5, dtype=np.float32))


@onnx_required
def test_predict_rejects_non_1d(tmp_path: Path) -> None:
    model_path = tmp_path / "head.onnx"
    _author_sigmoid_model(model_path, feature_dim=8)
    model = DiagnosticOnnxModel.load(model_path)
    with pytest.raises(ValueError, match="1-D feature vector"):
        model.predict(np.zeros((1, 8), dtype=np.float32))


@pytest.mark.skipif(not _HAS_TORCH, reason="needs the `train` extra (torch)")
def test_train_export_load_roundtrip(tmp_path: Path) -> None:
    """End-to-end: build head → train on tiny caller-supplied data →
    export ONNX → load via the inference wrapper → predict. Proves
    the export contract aligns with the inference loader. Runs only
    where torch is installed (skipped on the default CI image)."""
    from aimvision_ml.training.diagnostic_export import (
        build_head,
        export_to_onnx,
        train_head,
    )

    feature_dim = 12
    rng = np.random.default_rng(1)
    x = rng.standard_normal((32, feature_dim)).astype(np.float32)
    y = (rng.random((32, NUM_ATOMS)) > 0.5).astype(np.float32)

    head = build_head(feature_dim, hidden=16)
    train_head(head, x, y, epochs=3)
    out_path = export_to_onnx(head, feature_dim, tmp_path / "trained.onnx")
    assert out_path.is_file()

    model = DiagnosticOnnxModel.load(out_path)
    preds = model.predict(x[0])
    assert len(preds) == NUM_ATOMS
    for v in preds.values():
        assert 0.0 <= v <= 1.0
