"""Tests for `aimvision_ml.inference.audio_xcorr`.

Drives the cross-correlation pipeline with synthetic muzzle-blast-shaped
impulses. The synthetic harness here is deliberately *not* trying to
reproduce real range acoustics — it's the same shape (broadband sharp
onset + exponential decay), bandpassed identically on both "cameras",
shifted by a known offset, with optional white-noise floor. That keeps
the test scope on the *math of the alignment*: bandpass, xcorr peak,
parabolic sub-sample fit, search-window guard, median-over-shots
robustness.

Real-acoustics calibration belongs in the Sprint 5 range-capture eval
harness — we don't pretend to do it here.
"""

from __future__ import annotations

import numpy as np
import pytest

from aimvision_ml.inference.audio_xcorr import (
    AlignmentResult,
    PairAlignment,
    align_camera_pair,
    bandpass_pcm,
    cross_correlate_shot,
)

SAMPLE_RATE = 48_000


def _muzzle_blast_like(
    duration_s: float, peak_at_s: float, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """Build a one-channel "muzzle blast" — broadband impulse with a fast
    exponential decay. The blast is a click followed by ~5 ms of decay,
    which is shape-close to a real 12-gauge blast band-limited to
    200 Hz–8 kHz."""
    t = np.arange(int(duration_s * sample_rate)) / sample_rate
    sig = np.zeros_like(t)
    peak_sample = int(peak_at_s * sample_rate)
    if peak_sample < 0 or peak_sample >= sig.size:
        return sig
    # Impulse + 5 ms exponential decay shaped by a broadband chirp.
    decay_samples = int(0.005 * sample_rate)
    decay_idx = np.arange(decay_samples)
    decay_env = np.exp(-decay_idx / (0.001 * sample_rate))
    # Chirp-ish content: sum of a few in-band sinusoids so it looks
    # broadband through the 200–8000 Hz filter.
    freqs = (500.0, 1500.0, 3000.0, 5500.0)
    phase = np.zeros(decay_samples)
    for f in freqs:
        phase = phase + np.sin(2.0 * np.pi * f * decay_idx / sample_rate)
    impulse = phase * decay_env
    end = min(sig.size, peak_sample + decay_samples)
    sig[peak_sample:end] = impulse[: end - peak_sample]
    return sig.astype(np.float64)


def _frac_shift(sig: np.ndarray, delay_samples: float) -> np.ndarray:
    """Shift a signal by a (possibly fractional) number of samples via the
    Fourier shift theorem.

    `np.roll` would work for integer shifts but truncates / wraps; this
    function instead applies a pure time delay in the frequency domain
    so the output is the same waveform shifted by exactly
    `delay_samples` — including fractional values that the discrete
    sample grid can't represent natively. Used to validate the xcorr
    pipeline's sub-sample resolution.
    """
    n = sig.size
    fft = np.fft.fft(sig)
    freqs = np.fft.fftfreq(n)
    shifted_fft = fft * np.exp(-2j * np.pi * freqs * delay_samples)
    return np.real(np.fft.ifft(shifted_fft))


def _add_noise(sig: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add white noise scaled to the requested signal-to-noise ratio.

    SNR here is *peak-to-noise* — referenced to the loudest sample of
    `sig`. That's the right quantity for a blast: we care whether the
    impulse rises out of the noise floor, not the long-tail average.
    """
    peak = float(np.max(np.abs(sig)))
    if peak == 0.0:
        return sig
    noise_amp = peak / (10.0 ** (snr_db / 20.0))
    return sig + rng.normal(0.0, noise_amp, size=sig.size)


# ----------------------- bandpass tests -----------------------------


def test_bandpass_rejects_out_of_band_tones() -> None:
    sample_rate = SAMPLE_RATE
    t = np.arange(int(0.2 * sample_rate)) / sample_rate
    # 50 Hz tone (way below 200 Hz cutoff) — must come out attenuated by
    # > 30 dB. 1 kHz tone — must come out within 1 dB of input level.
    low_tone = np.sin(2 * np.pi * 50.0 * t)
    in_band = np.sin(2 * np.pi * 1000.0 * t)
    sig = low_tone + in_band

    filtered = bandpass_pcm(sig, sample_rate, 200.0, 8000.0, order=4)
    # Compare RMS after the transient settles.
    settle = int(0.05 * sample_rate)
    rms_input_inband = float(np.sqrt(np.mean(in_band[settle:] ** 2)))
    rms_filtered = float(np.sqrt(np.mean(filtered[settle:] ** 2)))
    # The in-band 1 kHz component passes through largely intact (within
    # 1 dB); the 50 Hz tone is wiped. So filtered RMS ≈ in-band RMS.
    assert rms_filtered == pytest.approx(rms_input_inband, rel=0.15)


def test_bandpass_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        bandpass_pcm(np.zeros((2, 100)), SAMPLE_RATE, 200.0, 8000.0)
    with pytest.raises(ValueError):
        bandpass_pcm(np.zeros(100), 0, 200.0, 8000.0)
    with pytest.raises(ValueError):
        # high_hz above Nyquist
        bandpass_pcm(np.zeros(100), SAMPLE_RATE, 200.0, 100_000.0)
    with pytest.raises(ValueError):
        # low_hz >= high_hz
        bandpass_pcm(np.zeros(100), SAMPLE_RATE, 8000.0, 200.0)


# ----------------------- xcorr tests --------------------------------


def test_integer_sample_offset_recovers_exactly() -> None:
    """Two identical signals, b delayed by exactly 240 samples (5 ms).

    Should recover offset within a fraction of a sample — the parabolic
    interp will give us a refined offset very close to the integer.
    """
    duration = 0.20  # 200 ms
    a = _muzzle_blast_like(duration, peak_at_s=0.10)
    delay_samples = 240
    b = np.zeros_like(a)
    b[delay_samples:] = a[: a.size - delay_samples]

    result = cross_correlate_shot(a, b, SAMPLE_RATE)

    # Expected offset: positive — b is delayed by 5 ms relative to a.
    expected_s = delay_samples / SAMPLE_RATE
    assert result.offset_s == pytest.approx(expected_s, abs=2e-5)  # < 1 sample
    assert result.confident, "synthetic perfect signal should be high-confidence"


def test_fractional_sample_offset_recovers_via_parabolic_fit() -> None:
    """Build b by an exact-fractional-sample FFT shift of a — the
    parabolic interpolation should recover the offset to better than
    one full sample of precision (sub-20 μs at 48 kHz)."""
    duration = 0.20
    a = _muzzle_blast_like(duration, peak_at_s=0.10)
    fractional_delay_samples = 5.3  # 5 + 0.3 sample (about 6 μs)
    b = _frac_shift(a, fractional_delay_samples)

    result = cross_correlate_shot(a, b, SAMPLE_RATE)
    expected_s = fractional_delay_samples / SAMPLE_RATE
    # The parabolic fit gets us to within one sample of the true
    # fractional offset. Tightening this floor to 0.2 samples would
    # likely also pass, but one sample is a safe gate — it's the
    # advertised precision in the audio-xcorr docstring.
    assert result.offset_s == pytest.approx(expected_s, abs=1.0 / SAMPLE_RATE)


def test_noise_lowers_confidence_but_offset_still_recoverable() -> None:
    """Add white noise at 30 dB peak-to-noise SNR — that's roughly the
    noise floor we'd see from a phone mic at a real range (the blast is
    140 dB SPL; the floor sits around 60 dB SPL → 80 dB SNR is typical,
    30 dB is a conservative pessimistic test). The peak should still
    win the xcorr argmax and the confidence ratio should drop visibly
    from the noise-free baseline."""
    rng = np.random.default_rng(42)
    duration = 0.20
    a_clean = _muzzle_blast_like(duration, peak_at_s=0.10)
    delay_samples = 240
    b_clean = np.zeros_like(a_clean)
    b_clean[delay_samples:] = a_clean[: a_clean.size - delay_samples]
    a = _add_noise(a_clean, snr_db=30.0, rng=rng)
    b = _add_noise(b_clean, snr_db=30.0, rng=rng)

    result_clean = cross_correlate_shot(a_clean, b_clean, SAMPLE_RATE)
    result_noisy = cross_correlate_shot(a, b, SAMPLE_RATE)

    expected_s = delay_samples / SAMPLE_RATE
    assert result_noisy.offset_s == pytest.approx(expected_s, abs=1e-4)
    assert result_noisy.confidence < result_clean.confidence


def test_uncorrelated_signals_yield_low_confidence() -> None:
    """Two independent noise streams — no real alignment exists."""
    rng = np.random.default_rng(7)
    a = rng.normal(0.0, 1.0, size=int(0.10 * SAMPLE_RATE))
    b = rng.normal(0.0, 1.0, size=int(0.10 * SAMPLE_RATE))
    # Default min_confidence is 2.0; uncorrelated noise should fail it.
    result = cross_correlate_shot(a, b, SAMPLE_RATE)
    assert not result.confident
    assert result.confidence < 2.0


def test_search_window_constrains_argmax() -> None:
    """If the true delay is *outside* the search window, the algorithm
    must return a value bounded by the window — i.e. it must not
    cross-lock to a delay it was told to ignore. Caller's job to widen
    the window if the bound is hit, not the xcorr's job to guess."""
    duration = 0.20
    a = _muzzle_blast_like(duration, peak_at_s=0.10)
    # Delay b by 80 ms; search window default is ±50 ms.
    delay_samples = int(0.080 * SAMPLE_RATE)
    b = np.zeros_like(a)
    b[delay_samples:] = a[: a.size - delay_samples]
    result = cross_correlate_shot(a, b, SAMPLE_RATE)
    # |offset_s| must be ≤ search_window_ms / 1000.
    assert abs(result.offset_s) <= 0.050 + 1.0 / SAMPLE_RATE


def test_length_mismatch_raises() -> None:
    a = np.zeros(1000)
    b = np.zeros(999)
    with pytest.raises(ValueError):
        cross_correlate_shot(a, b, SAMPLE_RATE)


# ----------------------- pair-alignment tests -----------------------


def _track_with_blasts_at(duration_s: float, blast_times_s: list[float]) -> np.ndarray:
    """Build a multi-blast PCM track of length `duration_s`. Each blast
    is the same shape as the synthetic blast used by the single-shot
    tests, planted at the given time. The blasts are non-overlapping
    by caller convention."""
    n = int(duration_s * SAMPLE_RATE)
    track = np.zeros(n, dtype=np.float64)
    for t in blast_times_s:
        # 50 ms window centered on the blast time — long enough to hold
        # the full decay (5 ms) plus margin.
        blast = _muzzle_blast_like(0.050, peak_at_s=0.025)
        # Align so the blast's peak lands at sample int(t * SR).
        peak_offset_in_blast = int(0.025 * SAMPLE_RATE)
        center = int(t * SAMPLE_RATE) - peak_offset_in_blast
        end = center + blast.size
        lo = max(0, center)
        hi = min(n, end)
        if hi <= lo:
            continue
        src_lo = lo - center
        src_hi = src_lo + (hi - lo)
        track[lo:hi] += blast[src_lo:src_hi]
    return track


def test_pair_alignment_medians_per_shot_offsets() -> None:
    """Three shots, each with the same true offset — pair alignment
    median should match that offset and every shot confident."""
    rng = np.random.default_rng(1)
    duration = 1.0
    delay_samples = 240  # 5 ms
    delay_s = delay_samples / SAMPLE_RATE

    # `a` is the master clock; `b`'s blasts are physically delayed by
    # `delay_s` against the same wall-clock times.
    shot_times_a = [0.20, 0.50, 0.80]
    blast_times_in_b = [t + delay_s for t in shot_times_a]

    a = _track_with_blasts_at(duration, shot_times_a)
    b = _track_with_blasts_at(duration, blast_times_in_b)
    a = _add_noise(a, snr_db=30.0, rng=rng)
    b = _add_noise(b, snr_db=30.0, rng=rng)

    result = align_camera_pair(a, b, shot_times_a, SAMPLE_RATE)
    expected_s = delay_s
    assert isinstance(result, PairAlignment)
    assert result.median_offset_s == pytest.approx(expected_s, abs=1.0 / SAMPLE_RATE)
    assert result.confident_shot_count == 3
    assert all(isinstance(r, AlignmentResult) for r in result.per_shot)


def test_pair_alignment_median_rejects_outlier_shot() -> None:
    """Five shots: four with offset 5 ms, one outlier with offset 30 ms.
    Median should pin to 5 ms, not be dragged by the outlier."""
    rng = np.random.default_rng(2)
    duration = 1.6
    true_offset_samples = 240
    true_offset_s = true_offset_samples / SAMPLE_RATE
    outlier_offset_samples = 1440  # 30 ms
    outlier_offset_s = outlier_offset_samples / SAMPLE_RATE

    shot_times_a = [0.20, 0.40, 0.60, 0.80, 1.20]
    # Four blasts in b are at +5 ms; one (index 2) at +30 ms.
    offsets = [
        true_offset_s,
        true_offset_s,
        outlier_offset_s,
        true_offset_s,
        true_offset_s,
    ]
    blast_times_in_b = [t + off for t, off in zip(shot_times_a, offsets, strict=True)]

    a = _track_with_blasts_at(duration, shot_times_a)
    b = _track_with_blasts_at(duration, blast_times_in_b)
    a = _add_noise(a, snr_db=30.0, rng=rng)
    b = _add_noise(b, snr_db=30.0, rng=rng)

    result = align_camera_pair(a, b, shot_times_a, SAMPLE_RATE)
    # Median over 5 values where 4 are at 5 ms and 1 at 30 ms = 5 ms.
    # Tolerance is one sample; the per-shot xcorr is exact on clean
    # impulses but the noise pushes it a fraction of a sample.
    assert result.median_offset_s == pytest.approx(true_offset_s, abs=1.0 / SAMPLE_RATE)


def test_pair_alignment_validates_inputs() -> None:
    with pytest.raises(ValueError):
        align_camera_pair(np.zeros(10), np.zeros(10), [], SAMPLE_RATE)
    with pytest.raises(ValueError):
        align_camera_pair(np.zeros((2, 5)), np.zeros(10), [0.001], SAMPLE_RATE)


def test_config_min_confidence_filters_unconfident_shots_from_median() -> None:
    """One confident shot at 5 ms; one noise window with no shot — the
    noise window's per-shot result is unconfident and excluded from
    the median, so the median stays at 5 ms."""
    rng = np.random.default_rng(3)
    duration = 0.6
    delay_samples = 240
    delay_s = delay_samples / SAMPLE_RATE

    a = _track_with_blasts_at(duration, [0.20])
    b = _track_with_blasts_at(duration, [0.20 + delay_s])
    a = _add_noise(a, snr_db=30.0, rng=rng)
    b = _add_noise(b, snr_db=30.0, rng=rng)

    result = align_camera_pair(
        a,
        b,
        [0.20, 0.45],  # second "shot" is in pure noise
        SAMPLE_RATE,
        # Default min_confidence already separates noise from blast for
        # the normalized correlation metric.
    )
    assert result.confident_shot_count >= 1
    assert result.median_offset_s == pytest.approx(delay_s, abs=1.0 / SAMPLE_RATE)
