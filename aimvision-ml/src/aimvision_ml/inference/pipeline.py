"""Per-shot orchestration: audio → pose → barrel → diagnostic.

Cite docs/ml-architecture.md §3 (live on-device pipeline). This module
defines the call sequence; the mobile core implements it on top of the
ONNX runtime + the Rust mpsc backpressure ladder.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from aimvision_ml.inference.audio_shot import AudioShotDetector, ShotEvent
from aimvision_ml.inference.barrel import BarrelDetection, BarrelDetector
from aimvision_ml.inference.diagnostic import DiagnosticHead
from aimvision_ml.inference.pose import PoseEstimator, PoseFrame
from aimvision_ml.schemas import ShotFeatureVector, ShotPrediction


@dataclass(frozen=True)
class ShotInputs:
    """Inputs to the per-shot diagnostic call.

    Built by the orchestrator from the audio event timestamp + the most
    recent pose / barrel windows. Time alignment is sub-10 ms with IMU
    fusion (ml-architecture.md §9); without IMU it's audio-anchored only.
    """

    shot_event: ShotEvent
    pose_window: list[PoseFrame]
    barrel_window: list[BarrelDetection]
    pcm_window: npt.NDArray[np.float32]
    imu_window: npt.NDArray[np.float32] | None
    videomae_embedding: npt.NDArray[np.float32] | None
    session_id: str
    shot_id: str


class LivePipeline:
    """Orchestrates the live-tier per-shot call sequence.

    The orchestrator's job is alignment + assembling the feature vector;
    the per-modality models are injected so eval scripts can swap stubs in.
    Backpressure / drop policy is the host runtime's responsibility (see
    docs/performance-budgets.md §5.2).
    """

    def __init__(
        self,
        audio: AudioShotDetector,
        pose: PoseEstimator,
        barrel: BarrelDetector,
        diagnostic: DiagnosticHead,
    ) -> None:
        self.audio = audio
        self.pose = pose
        self.barrel = barrel
        self.diagnostic = diagnostic

    def diagnose(self, inputs: ShotInputs) -> ShotPrediction:
        """Run the diagnostic head on assembled per-shot features."""
        features = ShotFeatureVector(
            shot_id=inputs.shot_id,
            session_id=inputs.session_id,
            pose_keypoints=[f.keypoints.tolist() for f in inputs.pose_window] or None,
            imu_trace=inputs.imu_window.tolist() if inputs.imu_window is not None else None,
            audio_features=inputs.pcm_window.tolist() if inputs.pcm_window.size else None,
            videomae_embedding=(
                inputs.videomae_embedding.tolist()
                if inputs.videomae_embedding is not None
                else None
            ),
            pose_available=bool(inputs.pose_window),
            imu_available=inputs.imu_window is not None,
            audio_available=bool(inputs.pcm_window.size),
            videomae_available=inputs.videomae_embedding is not None,
        )
        return self.diagnostic.infer(features)
