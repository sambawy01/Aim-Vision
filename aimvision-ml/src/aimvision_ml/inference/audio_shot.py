"""Audio shot detector — interface only.

The live tier runs a CRNN (or YAMNet-tiny) on 50ms-hop / 200ms-window PCM
per docs/performance-budgets.md §5.1. The model itself is exported to
ONNX and shipped with the mobile binaries; this module defines the
Python-side wrapper used during eval and post-session re-detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class ShotEvent:
    """One detected shot.

    `confidence` is the calibrated probability of a real muzzle blast vs.
    background / clay impact / wind. The IMU tap-detect fusion gate (per
    ml-architecture.md §9) tightens this to sub-10ms timing post-fusion.
    """

    timestamp_s: float
    confidence: float
    chunk_index: int


class AudioShotDetector(Protocol):
    """ONNX-runtime-backed wrapper protocol.

    The training repo only declares the interface; the mobile core
    (aimvision-camera-core) consumes the ONNX export at runtime.
    """

    def detect(self, pcm: npt.NDArray[np.float32], sample_rate: int) -> list[ShotEvent]:
        """Run the detector over a PCM buffer and return events."""
        ...


class StubAudioShotDetector:
    """Deterministic stub for unit tests.

    Returns a single shot event at the loudest 50 ms hop. Not used in
    production; exists so eval-script wiring is exercisable without
    onnxruntime + a real model file.
    """

    def detect(self, pcm: npt.NDArray[np.float32], sample_rate: int) -> list[ShotEvent]:
        if pcm.ndim != 1:
            raise ValueError("expected mono PCM")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        hop = max(1, int(0.05 * sample_rate))
        if pcm.size < hop:
            return []
        # RMS energy per hop — peak hop is the "shot".
        n_hops = pcm.size // hop
        energies = np.array(
            [float(np.sqrt(np.mean(pcm[i * hop : (i + 1) * hop] ** 2))) for i in range(n_hops)],
            dtype=np.float32,
        )
        peak = int(np.argmax(energies))
        return [
            ShotEvent(
                timestamp_s=peak * 0.05,
                confidence=float(np.clip(energies[peak] * 5.0, 0.0, 1.0)),
                chunk_index=peak,
            )
        ]
