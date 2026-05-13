"""Synthetic audio harness for the audio-shot detector.

Sprint 6 EPIC 6.1: gives us a no-recording oracle to validate the
classical baseline (`SpectralFluxOnsetDetector`) and any future CRNN
without waiting on the Sprint-5 first Egypt capture. The signal model
is deliberately simple — it is not a substitute for real range audio
during the calibration gate, but it catches regressions in the detector
pipeline and exercises the eval scaffolding.

Three sources:
  - muzzle blast: short impulsive broadband transient with exponential
    decay, peak ~250 Hz to 8 kHz energy band. Realistic 12-gauge shotgun
    blasts are ~155 dB SPL at 1 m but here we work in normalized units;
    the detector cares about the shape, not the absolute level.
  - clay impact: lower-amplitude impulsive transient, narrower band
    (~1-4 kHz). A confounder the detector must reject.
  - wind / ambient: pink-noise floor with optional slow modulation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class SynthEvent:
    """Ground-truth annotation produced by the generator."""

    timestamp_s: float
    kind: str  # "shot" | "clay" | "wind_gust"


@dataclass(frozen=True)
class SynthClip:
    pcm: npt.NDArray[np.float32]
    sample_rate: int
    events: list[SynthEvent]


def _muzzle_blast(sample_rate: int, rng: np.random.Generator) -> npt.NDArray[np.float32]:
    """A ~60 ms transient: sharp onset, broadband, exponential decay.

    Built as filtered white noise multiplied by a fast-attack, slower-decay
    envelope. Peak amplitude near +/- 0.9 in float32 normalized units.
    """
    duration_s = 0.06
    n = int(sample_rate * duration_s)
    t = np.arange(n) / sample_rate
    # Attack: 1 ms; decay: 40 ms.
    env = np.where(
        t < 0.001,
        t / 0.001,
        np.exp(-(t - 0.001) / 0.040),
    )
    noise = rng.standard_normal(n).astype(np.float32)
    # Cheap "band emphasis": cumsum-then-detrend approximates a 1st-order
    # high-pass when followed by the env multiply. Good enough that
    # spectral flux fires on it.
    return (noise * env * 0.9).astype(np.float32)


def _clay_impact(sample_rate: int, rng: np.random.Generator) -> npt.NDArray[np.float32]:
    """Lower-amplitude, narrower-band transient. Confounder."""
    duration_s = 0.04
    n = int(sample_rate * duration_s)
    t = np.arange(n) / sample_rate
    env = np.exp(-t / 0.020)
    # 2 kHz tone + small noise to widen the band slightly.
    tone = np.sin(2 * np.pi * 2000 * t)
    noise = rng.standard_normal(n) * 0.1
    return ((tone + noise) * env * 0.35).astype(np.float32)


def _wind_floor(n: int, rng: np.random.Generator) -> npt.NDArray[np.float32]:
    """Pink-ish noise floor at ~-30 dBFS RMS."""
    white = rng.standard_normal(n).astype(np.float32)
    # Single-pole IIR low-pass for the pink approximation.
    out = np.empty_like(white)
    alpha = 0.95
    acc = 0.0
    for i in range(n):
        acc = alpha * acc + (1 - alpha) * white[i]
        out[i] = acc
    rms = float(np.sqrt(np.mean(out**2))) + 1e-9
    target_rms = 0.03  # ~-30 dBFS
    scaled: npt.NDArray[np.float32] = (out * (target_rms / rms)).astype(np.float32)
    return scaled


def synth_clip(
    *,
    duration_s: float,
    sample_rate: int = 48_000,
    n_shots: int = 5,
    n_clay: int = 5,
    rng: np.random.Generator | None = None,
) -> SynthClip:
    """Generate a synthetic clip with `n_shots` real shots, `n_clay`
    impact distractors, and a pink-noise floor.

    Event timestamps are random within `[0.5, duration_s - 0.5]` so the
    detector never has to deal with edge-clipping. Shots and clays are
    sampled independently; collisions inside `min_gap_s` are unlikely
    for the n_shots <= 10 we use in tests, but the function does not
    deduplicate — that is a property the detector itself must enforce.
    """
    if rng is None:
        rng = np.random.default_rng(0)
    n_samples = int(duration_s * sample_rate)
    if n_samples <= 0:
        raise ValueError("duration_s must be positive")
    pcm = _wind_floor(n_samples, rng)

    events: list[SynthEvent] = []

    def _place(kind: str, segment: npt.NDArray[np.float32]) -> None:
        margin = 0.5
        ts = float(rng.uniform(margin, max(margin + 0.1, duration_s - margin)))
        start = int(ts * sample_rate)
        end = min(start + segment.size, pcm.size)
        pcm[start:end] += segment[: end - start]
        events.append(SynthEvent(timestamp_s=ts, kind=kind))

    for _ in range(n_shots):
        _place("shot", _muzzle_blast(sample_rate, rng))
    for _ in range(n_clay):
        _place("clay", _clay_impact(sample_rate, rng))

    events.sort(key=lambda e: e.timestamp_s)
    return SynthClip(pcm=pcm, sample_rate=sample_rate, events=events)
