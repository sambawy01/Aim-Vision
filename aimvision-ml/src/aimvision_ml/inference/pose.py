"""RTMPose-Lite ONNX wrapper interface.

Live-tier pose at 8–12 fps on phone NPUs. Replaces MediaPipe BlazePose per
ml-architecture.md §4. The training repo defines the interface; the mobile
core consumes the ONNX export at runtime through Core ML / NNAPI / QNN.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class PoseFrame:
    """One frame's worth of keypoints in COCO-17 topology.

    `keypoints` is shape ``(17, 3)`` with columns ``(x, y, score)``.
    Wholebody (133 keypoints, hands + face) runs in the post-session tier
    only; live tier exposes only the COCO-supportable signals.
    """

    keypoints: npt.NDArray[np.float32]
    timestamp_s: float
    inference_ms: float


class PoseEstimator(Protocol):
    """Interface for the RTMPose-Lite live wrapper."""

    def infer(self, frame_rgb: npt.NDArray[np.uint8]) -> PoseFrame: ...

    def warmup(self) -> None: ...


class StubPoseEstimator:
    """Test stub: returns zero keypoints with stable shape."""

    def infer(self, frame_rgb: npt.NDArray[np.uint8]) -> PoseFrame:
        if frame_rgb.ndim != 3 or frame_rgb.shape[2] != 3:
            raise ValueError("expected HxWx3 RGB frame")
        kp = np.zeros((17, 3), dtype=np.float32)
        return PoseFrame(keypoints=kp, timestamp_s=0.0, inference_ms=0.0)

    def warmup(self) -> None:
        return None
