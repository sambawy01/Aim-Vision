"""ONNX inference for the multi-task diagnostic head (ml-architecture.md §8).

This is the *inference plumbing* for the diagnostic head: load an
exported ONNX model, run a per-shot feature vector through it, and
map the 15 sigmoid outputs back onto the canonical taxonomy atoms
(`aimvision_ml.taxonomy`).

# No weights ship in this repo (intentional)

Per the build decision: there is **no trained model checked in**.
The diagnostic head must be trained on real Egypt range data on a
GPU (Sprint 9), which doesn't exist yet. `load_or_none()` therefore
returns `None` when no model file is present, and the post-session
pipeline degrades gracefully (no diagnostic events emitted) rather
than fabricating predictions. The training + export side lives in
`aimvision_ml.training.diagnostic_export` and is torch-gated.

# Contract

- Input: a 1-D float32 feature vector (or a 2-D batch). The feature
  layout is defined by the per-shot feature extractor; this module
  only asserts the dimensionality the model declares.
- Output: one sigmoid probability per atom, in `all_categories()`
  order (multi-label — atoms co-occur, so this is NOT a softmax).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from aimvision_ml.taxonomy import DiagnosticCategory, all_categories

if TYPE_CHECKING:
    import onnxruntime as ort

# Deterministic atom order the model's output columns map to. The
# exporter MUST emit columns in this exact order; the eval harness +
# this loader both key off `all_categories()` so there's one source
# of truth.
ATOM_ORDER: tuple[DiagnosticCategory, ...] = tuple(all_categories())
NUM_ATOMS = len(ATOM_ORDER)


class DiagnosticOnnxModel:
    """Thin wrapper over an onnxruntime session for the diagnostic head."""

    def __init__(self, session: ort.InferenceSession) -> None:
        self._session = session
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1:
            raise ValueError(f"expected exactly 1 input, got {len(inputs)}")
        if len(outputs) != 1:
            raise ValueError(f"expected exactly 1 output, got {len(outputs)}")
        self._input_name = inputs[0].name
        self._output_name = outputs[0].name
        # The model's declared feature width (last input dim). Used to
        # validate callers before paying for a session.run().
        shape = inputs[0].shape
        self._feature_dim = shape[-1] if shape and isinstance(shape[-1], int) else None

    @property
    def feature_dim(self) -> int | None:
        return self._feature_dim

    @classmethod
    def load(cls, path: str | Path) -> DiagnosticOnnxModel:
        """Load a model from disk. Raises FileNotFoundError if absent."""
        import onnxruntime as ort

        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"no diagnostic ONNX model at {p}")
        session = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
        return cls(session)

    @classmethod
    def load_or_none(cls, path: str | Path | None) -> DiagnosticOnnxModel | None:
        """Load if a model file exists, else None.

        This is the production gate: with no trained model shipped,
        callers get None and skip diagnostic emission rather than
        fabricating outputs.
        """
        if path is None:
            return None
        if not Path(path).is_file():
            return None
        return cls.load(path)

    def predict(self, features: np.ndarray) -> dict[DiagnosticCategory, float]:
        """Run a single feature vector → per-atom probabilities.

        `features` is a 1-D array. Returns a dict keyed by atom in
        `ATOM_ORDER`. For batches use `predict_batch`.
        """
        vec = np.asarray(features, dtype=np.float32)
        if vec.ndim != 1:
            raise ValueError(f"expected a 1-D feature vector, got shape {vec.shape}")
        probs = self.predict_batch(vec.reshape(1, -1))[0]
        return dict(zip(ATOM_ORDER, (float(p) for p in probs), strict=True))

    def predict_batch(self, features: np.ndarray) -> np.ndarray:
        """Run a 2-D batch (rows = shots) → (rows, NUM_ATOMS) probs."""
        mat = np.asarray(features, dtype=np.float32)
        if mat.ndim != 2:
            raise ValueError(f"expected a 2-D batch, got shape {mat.shape}")
        if self._feature_dim is not None and mat.shape[1] != self._feature_dim:
            raise ValueError(f"model expects {self._feature_dim} features, got {mat.shape[1]}")
        out = self._session.run([self._output_name], {self._input_name: mat})[0]
        result = np.asarray(out, dtype=np.float64)
        if result.shape != (mat.shape[0], NUM_ATOMS):
            raise ValueError(
                f"model output {result.shape} != expected {(mat.shape[0], NUM_ATOMS)}; "
                "the export is misaligned with the taxonomy"
            )
        return result
