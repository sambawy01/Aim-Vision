"""YOLOv8n int8 barrel-detector wrapper interface.

Live: subsampled to 5–8 fps per ml-architecture.md §5. Post-session uses
SAM2 mask propagation initialized from a YOLOv8x detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class BarrelDetection:
    """One barrel-bbox detection in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    timestamp_s: float


class BarrelDetector(Protocol):
    def infer(self, frame_rgb: npt.NDArray[np.uint8]) -> BarrelDetection | None: ...


class StubBarrelDetector:
    """Test stub: returns None (no detection)."""

    def infer(self, frame_rgb: npt.NDArray[np.uint8]) -> BarrelDetection | None:
        if frame_rgb.ndim != 3 or frame_rgb.shape[2] != 3:
            raise ValueError("expected HxWx3 RGB frame")
        return None
