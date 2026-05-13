"""Audio shot detector — interface + classical baseline + ONNX wrapper.

The live tier runs a CRNN (or YAMNet-tiny) on 50ms-hop / 200ms-window PCM
per docs/performance-budgets.md §5.1. The model itself is exported to
ONNX and shipped with the mobile binaries; this module defines the
Python-side wrapper used during eval and post-session re-detection.

Sprint 6 EPIC 6.1 adds an explainable classical baseline,
`SpectralFluxOnsetDetector`, that:

  1. Computes short-time Fourier transform on the PCM stream.
  2. Derives spectral flux — positive half-wave rectified diff of the
     log-magnitude spectrogram.
  3. Adaptive threshold = median + k * MAD over a sliding window. This
     is robust to range-floor noise (talking, machinery) without a
     dataset-specific calibration.
  4. Impulsivity gate rejects sustained sources (wind, motor, ambient
     range PA): peak frame must exceed neighbors by >= peak_to_neighbor_db.
  5. Minimum inter-event gap suppresses double-trigger on a single blast.

The baseline is a useful reference for the CRNN: it gives us a no-train
oracle for synthetic data and a fallback the mobile binary can carry as
a sanity-check signal alongside the learned detector. Targets per
ml-architecture.md §9: recall ≥ 0.95 on muzzle blasts, FPR ≤ 0.1/min on
range ambience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt
from scipy.signal import stft


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


@dataclass(frozen=True)
class SpectralFluxConfig:
    """Hyperparameters for SpectralFluxOnsetDetector.

    Defaults targeted at 48 kHz mono PCM from a phone mic in a range
    setting. The mobile capture path resamples to 48 kHz before handing
    the buffer to the detector (camera-core SDK contract).
    """

    window_ms: float = 25.0
    hop_ms: float = 10.0
    """Sliding window length for the adaptive threshold (median + k*MAD)."""
    threshold_window_s: float = 1.0
    """k coefficient in the threshold = median + k * MAD formula. Higher
    rejects more, lower catches more. Tuned on the synthetic harness; can
    be retuned per range once labelled data lands (Sprint 5 EPIC 5.5)."""
    threshold_k: float = 4.0
    """Minimum dB margin a peak must clear over its background hops.
    Background is sampled ±background_offset_frames away from the peak so
    the impulsivity check is not contaminated by the blast's own decay
    tail. Suppresses sustained sources (wind, generators)."""
    peak_to_neighbor_db: float = 4.0
    """Frame offset used to sample the background for the impulsivity
    gate. Default ≈ 100 ms at the default hop, well past the typical
    blast envelope decay so the comparison is shot-vs-floor."""
    background_offset_frames: int = 10
    """Minimum gap between two consecutive shot detections, in seconds.
    A skeet pair fires at ~300 ms apart so the floor is well below that."""
    min_gap_s: float = 0.12


class SpectralFluxOnsetDetector:
    """Classical baseline that runs without a learned model.

    Reads as a Protocol-conforming `AudioShotDetector` so any code that
    accepts the learned ONNX wrapper accepts this too.
    """

    def __init__(self, config: SpectralFluxConfig | None = None) -> None:
        self.config = config or SpectralFluxConfig()

    def detect(self, pcm: npt.NDArray[np.float32], sample_rate: int) -> list[ShotEvent]:
        if pcm.ndim != 1:
            raise ValueError("expected mono PCM")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        cfg = self.config
        nperseg = max(8, int(sample_rate * cfg.window_ms / 1000))
        noverlap = max(0, nperseg - int(sample_rate * cfg.hop_ms / 1000))
        if pcm.size < nperseg:
            return []

        _, _, spec = stft(
            pcm.astype(np.float64),
            fs=sample_rate,
            nperseg=nperseg,
            noverlap=noverlap,
            boundary=None,
            padded=False,
        )
        mag = np.abs(spec)
        # Avoid log(0); 1e-10 keeps log-mag finite and stable.
        log_mag = np.log10(mag + 1e-10)

        # Spectral flux: sum of positive half-wave rectified diff between
        # adjacent frames. Muzzle blasts have a sharp broadband onset that
        # flux captures cleanly while wind, which is slowly-varying low-mid
        # band, gives a low flux signature.
        diff = np.diff(log_mag, axis=1)
        flux = np.sum(np.maximum(diff, 0.0), axis=0)
        if flux.size == 0:
            return []

        hop_s = (nperseg - noverlap) / sample_rate
        win_frames = max(3, int(cfg.threshold_window_s / hop_s))

        events: list[ShotEvent] = []
        last_emit_frame = -10_000
        min_gap_frames = max(1, int(cfg.min_gap_s / hop_s))

        for i in range(flux.size):
            lo = max(0, i - win_frames)
            hi = min(flux.size, i + win_frames + 1)
            window = flux[lo:hi]
            median = float(np.median(window))
            mad = float(np.median(np.abs(window - median)))
            # MAD->std factor 1.4826 is well-known; keeps the k coefficient
            # interpretable as "this many robust-stds above the floor."
            threshold = median + cfg.threshold_k * (mad * 1.4826 + 1e-12)
            if flux[i] < threshold:
                continue

            # Impulsivity: compare this frame's broadband energy to the
            # mean of frames sampled `background_offset_frames` away on
            # each side. Sampling far from the peak keeps the blast's own
            # decay out of the background estimate so a real shot still
            # clears the gate while sustained sources fail.
            off = cfg.background_offset_frames
            bg_frames: list[npt.NDArray[np.float64]] = []
            if i - off >= 0:
                bg_frames.append(log_mag[:, max(0, i - off - 2) : i - off + 1])
            if i + off < log_mag.shape[1]:
                bg_frames.append(log_mag[:, i + off : min(log_mag.shape[1], i + off + 3)])
            background = np.concatenate(bg_frames, axis=1) if bg_frames else log_mag[:, :0]
            bg_db = 0.0 if background.size == 0 else 20.0 * float(np.mean(background))
            peak_db = 20.0 * float(np.mean(log_mag[:, i]))
            if peak_db - bg_db < cfg.peak_to_neighbor_db:
                continue

            if i - last_emit_frame < min_gap_frames:
                # Local maximum suppression: if this frame is more peaky
                # than the last-emitted one, replace; else drop.
                if events and flux[i] > flux[last_emit_frame]:
                    events[-1] = _make_event(flux, i, threshold, hop_s)
                    last_emit_frame = i
                continue

            events.append(_make_event(flux, i, threshold, hop_s))
            last_emit_frame = i

        return events


def _make_event(flux: npt.NDArray[np.float64], i: int, threshold: float, hop_s: float) -> ShotEvent:
    """Build a ShotEvent with a sigmoid-mapped confidence.

    Confidence is the sigmoid of the flux margin above threshold, scaled
    so that 2x threshold maps to ~0.88. Not calibrated probabilistically
    — calibration lands when the CRNN does, with the ECE gate.
    """
    margin = flux[i] - threshold
    scale = max(threshold, 1e-6)
    raw = margin / scale
    conf = float(1.0 / (1.0 + np.exp(-2.0 * raw)))
    return ShotEvent(timestamp_s=i * hop_s, confidence=conf, chunk_index=i)
