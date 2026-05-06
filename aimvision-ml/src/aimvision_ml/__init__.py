"""AIMVISION ML — training, evaluation, ONNX export, and registry.

Public surface intentionally narrow; submodules are imported on demand to
keep the lightweight install path free of torch / mmpose / onnxruntime.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
