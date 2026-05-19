"""Audio cross-correlation alignment for multi-camera capture.

Implements the fine-alignment layer specified in
`docs/multi-camera-sync-spec.md` §3.2, scoped to the dev-mode phone
backend (ADR-0009 slice 4) where no `!MSYNC` is available. The same
pipeline runs in the Hero 13 + Hero 13 path; phone-only just doesn't
have an MSYNC bootstrap, so the coarse bracket has to come from the
session start NTP-ish handshake instead.

# Pipeline

For one camera pair (a, b):

  1. **Bandpass 200 Hz–8 kHz.** Range PA, generator hum, and wind sit
     mostly below 200 Hz; phone-mic high-end noise sits above 8 kHz.
     The muzzle blast is broadband but its discriminating energy is in
     this band (sharp onset + non-tonal). A 4th-order Butterworth
     applied forward-backward (`filtfilt`) gives zero phase shift —
     critical, because a phase-shifting filter would itself introduce
     a timing bias we'd then "discover" as a sync offset.

  2. **Window around each shot.** Per shot timestamp `t_s`, take
     `±window_s / 2` of PCM from each camera. Window length is a
     trade-off: longer = more impulses contribute to xcorr, shorter
     = less risk of pulling in a different shot's blast on a skeet
     pair fired ~300 ms apart. 100 ms covers the full impulse +
     decay tail of a 12-gauge blast at typical range distances.

  3. **Cross-correlate.** `scipy.signal.correlate(a, b, mode='full')`
     computes the full discrete cross-correlation. We restrict the
     argmax search to `±search_window_ms` to keep an unrelated peak
     (a different shot, an echo) from winning the alignment. The
     search window must be greater than the coarse-bracket
     uncertainty — defaults assume ±50 ms which is conservative for
     phone-pair capture (we can run handshake-clock-skew up to 25 ms
     and the spec budgets ±50 ms for that bootstrap).

  4. **Sub-sample peak refinement.** The discrete argmax lands on a
     sample index — at 48 kHz that's 20.8 μs resolution. The blast's
     onset is sharper than the sample rate so we can do better with a
     parabolic fit on the three samples around the peak. This is the
     classical technique from audio time-delay estimation; it gives
     fractional-sample precision and pushes the alignment well into
     the sub-millisecond floor the spec calls for.

  5. **Confidence.** Normalized cross-correlation coefficient —
     `peak / (||a|| * ||b||)` — gives a [0, 1] metric where 1.0 is
     perfect alignment of identical signals and 1/sqrt(N) is the
     floor for uncorrelated noise. Real cross-camera muzzle blasts
     land in 0.5–0.95; the default `min_confidence` is 0.3 so the
     caller fails open on poor shots and falls back to coarse or
     marks the shot unaligned.

# Pair-level driver

`align_camera_pair` runs the per-shot pipeline across a list of
matching shots and returns the *median* offset. Median (not mean)
because one bad shot — say, an echo confusing the xcorr peak —
shouldn't drag the whole-session alignment. The per-shot results are
also returned so the caller can debug or apply per-shot drift
correction.

# Why this lives in `aimvision-ml/inference/` not `aimvision-camera-core/`

The xcorr math is pure numpy/scipy and runs on the post-session
pipeline; the Rust camera core only needs the *answer*, not the
arithmetic. Keeping it in Python means we can iterate on the algorithm
(window length, bandpass band, fallback heuristics) without
recompiling a Rust crate or shipping a new mobile binary. The result
of `align_camera_pair` is what gets stored as
`session_clock_offset_ns` in the backend `Recording` row (slice 2's
`source_kind` migration didn't yet wire this field; that's the bench
integration in a future slice).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, correlate, correlation_lags, filtfilt


@dataclass(frozen=True)
class XcorrConfig:
    """Hyperparameters for the audio cross-correlation pipeline.

    Defaults target 48 kHz mono PCM from a phone mic at typical range
    distances. Retune `search_window_ms` upward if the coarse-bracket
    handshake is looser than ±50 ms; never push it past ±250 ms because
    a skeet pair's second clay can fire that fast and we'd risk
    cross-locking to the wrong blast.
    """

    bandpass_low_hz: float = 200.0
    bandpass_high_hz: float = 8000.0
    """Butterworth filter order. 4 gives a ~24 dB/oct rolloff which is
    sharp enough to suppress the sub-200 Hz wind band without ringing.
    `filtfilt` doubles the effective order to 8 (zero phase shift)."""
    bandpass_order: int = 4
    """Per-shot PCM window length, in seconds. 100 ms covers the full
    12-gauge blast + decay tail; shorter risks missing late energy,
    longer risks pulling in a neighbouring blast on a skeet pair."""
    window_s: float = 0.10
    """Cross-correlation search range, in milliseconds — the argmax
    is restricted to ±this many ms. Must exceed the coarse-bracket
    uncertainty (±25 ms handshake skew → ±50 ms default is safe)."""
    search_window_ms: float = 50.0
    """Minimum acceptable normalized correlation coefficient. The
    confidence is `peak / (||a|| * ||b||)`, i.e. the Pearson-style
    [0, 1] normalized cross-correlation peak after zero-meaning each
    input. Per-shot results below this threshold are still returned
    (so the caller can debug) but are flagged as low-confidence; the
    pair-level driver excludes them from the median by default.

    Uncorrelated gaussian noise produces normalized peaks around
    1 / sqrt(N) ≈ 0.014 at the default 100 ms / 48 kHz window
    (4800 samples). Real blasts share most of their bandpassed
    energy across cameras and produce peaks in the 0.5–0.95 range.
    0.3 keeps a comfortable margin between the two regimes while
    still passing real blasts captured through cheap phone mics."""
    min_confidence: float = 0.3


@dataclass(frozen=True)
class AlignmentResult:
    """Per-shot cross-correlation result.

    `offset_s` is signed: a positive value means b's signal arrives
    **later** than a's (so we'd subtract `offset_s` from b's
    timestamps to align them onto a's clock). The sign is set by
    `cross_correlate_shot`'s post-xcorr negation — read the comment
    there for the underlying scipy convention.

    `sample_offset` is the parabolic-fit-refined fractional-sample
    lag, with the same sign as `offset_s`. Use it when chaining
    results downstream so you avoid two rounds of floating-point
    quantization.
    """

    offset_s: float
    sample_offset: float
    confidence: float
    peak_value: float
    confident: bool


@dataclass(frozen=True)
class PairAlignment:
    """Whole-pair median alignment plus the per-shot detail.

    `median_offset_s` is the canonical session offset (use this to
    align b's timestamps onto a's). `per_shot` gives the unaltered
    per-shot results so the caller can detect outliers, plot drift,
    or fall back to a different shot if the median's confidence is
    low.
    """

    median_offset_s: float
    confident_shot_count: int
    per_shot: tuple[AlignmentResult, ...]


def _validate_pcm_pair(
    a: npt.NDArray[np.floating], b: npt.NDArray[np.floating], sample_rate_hz: int
) -> None:
    if a.ndim != 1 or b.ndim != 1:
        raise ValueError("expected mono PCM (1-D arrays) for both signals")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")


def bandpass_pcm(
    pcm: npt.NDArray[np.floating],
    sample_rate_hz: int,
    low_hz: float,
    high_hz: float,
    order: int = 4,
) -> npt.NDArray[np.float64]:
    """Zero-phase Butterworth bandpass on a mono PCM stream.

    Returns a `float64` array regardless of the input dtype — sub-sample
    arithmetic later in the pipeline needs the headroom. `filtfilt`
    applies the filter forward then backward, so the effective order
    doubles and phase shift cancels.
    """
    if pcm.ndim != 1:
        raise ValueError("expected mono PCM")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    nyq = sample_rate_hz / 2.0
    if not 0.0 < low_hz < high_hz < nyq:
        raise ValueError(f"need 0 < low_hz ({low_hz}) < high_hz ({high_hz}) < nyquist ({nyq})")
    # SciPy's `butter` with `Wn=(low, high)` normalized to the Nyquist
    # gives us a bandpass section directly. `output='sos'` is more
    # numerically stable than `'ba'` for higher orders but butter at
    # order=4 is fine with `'ba'` and yields a simpler call to filtfilt.
    b_coef, a_coef = butter(order, [low_hz / nyq, high_hz / nyq], btype="band")
    # `filtfilt` returns `Any` per scipy's stubs; we know it's
    # `ndarray[float64]` given the inputs.
    out: npt.NDArray[np.float64] = filtfilt(b_coef, a_coef, pcm.astype(np.float64))
    return out


def _parabolic_subsample_offset(y_minus: float, y_zero: float, y_plus: float) -> float:
    """Three-point parabolic peak interpolation around the discrete argmax.

    Returns the fractional offset of the parabola's vertex relative to
    the central sample (sample 0). Standard derivation: fit a parabola
    through (-1, y_minus), (0, y_zero), (1, y_plus) and solve for the
    vertex's x-coordinate.

    Returns 0.0 if the three points are colinear (denominator vanishes)
    or if the fit would extrapolate outside the [-0.5, 0.5] interval
    (extreme curvature is usually a noisy fit, not a real sub-sample
    refinement).
    """
    denom = y_minus - 2.0 * y_zero + y_plus
    if denom == 0.0:
        return 0.0
    delta = 0.5 * (y_minus - y_plus) / denom
    # Defensive clamp: the parabolic fit should give |delta| < 0.5 at a
    # true peak; values outside that window indicate either two adjacent
    # peaks or a noisy correlation function. Clamping prevents a
    # nonsensical sub-sample offset from leaking through.
    if delta < -0.5 or delta > 0.5:
        return 0.0
    return delta


def cross_correlate_shot(
    a: npt.NDArray[np.floating],
    b: npt.NDArray[np.floating],
    sample_rate_hz: int,
    config: XcorrConfig | None = None,
) -> AlignmentResult:
    """Cross-correlate two equal-length PCM windows around a single shot.

    Pre-conditions: caller has already extracted matching windows from
    each camera's PCM stream — typically `pcm[t-window/2 : t+window/2]`
    with `t` from each camera's shot detector. The windows MUST be the
    same length; cross-correlation between mismatched lengths
    misattributes timing.

    The signals are bandpassed inside this function; pass raw PCM in.
    """
    cfg = config or XcorrConfig()
    _validate_pcm_pair(a, b, sample_rate_hz)
    if a.size != b.size:
        raise ValueError(f"a and b must be equal-length windows; got {a.size} vs {b.size}")

    a_bp = bandpass_pcm(
        a, sample_rate_hz, cfg.bandpass_low_hz, cfg.bandpass_high_hz, cfg.bandpass_order
    )
    b_bp = bandpass_pcm(
        b, sample_rate_hz, cfg.bandpass_low_hz, cfg.bandpass_high_hz, cfg.bandpass_order
    )

    # Zero-mean each signal. The bandpass already removed DC but a
    # window of a strongly-asymmetric blast can carry a residual bias
    # that biases the unnormalized correlation peak.
    a_bp = a_bp - float(np.mean(a_bp))
    b_bp = b_bp - float(np.mean(b_bp))

    # `correlate(a, b)` with mode='full' gives output of length
    # `len(a) + len(b) - 1`. `correlation_lags` returns the integer lag
    # of *a relative to b* in scipy's convention: positive lag means a
    # leads b. So if b is "a delayed by D samples", the peak lands at
    # lag = -D. We negate further down so callers can read `offset_s > 0
    # ⇒ b later than a`, which is the convention the rest of the
    # multi-camera-sync code uses.
    xcorr = correlate(a_bp, b_bp, mode="full", method="auto")
    lags = correlation_lags(a_bp.size, b_bp.size, mode="full")

    max_lag_samples = int(round(cfg.search_window_ms / 1000.0 * sample_rate_hz))
    mask = (lags >= -max_lag_samples) & (lags <= max_lag_samples)
    if not np.any(mask):
        # Search window is narrower than one sample — degenerate.
        return AlignmentResult(
            offset_s=0.0,
            sample_offset=0.0,
            confidence=0.0,
            peak_value=0.0,
            confident=False,
        )

    masked = xcorr[mask]
    masked_lags = lags[mask]
    # Operate on the magnitude so a strong anticorrelation (peak negative
    # but large absolute value) doesn't get masked by the unsigned argmax.
    # In practice muzzle blasts share polarity across mics so the peak
    # *is* positive, but we don't want to assume it.
    mag = np.abs(masked)
    peak_idx = int(np.argmax(mag))
    peak_value = float(masked[peak_idx])
    peak_lag = int(masked_lags[peak_idx])

    # Parabolic sub-sample refinement around the peak — only safe when
    # the peak isn't at a search-window boundary.
    sub_offset = 0.0
    if 0 < peak_idx < mag.size - 1:
        sub_offset = _parabolic_subsample_offset(
            float(mag[peak_idx - 1]), float(mag[peak_idx]), float(mag[peak_idx + 1])
        )

    fractional_lag = float(peak_lag) + sub_offset
    # Sign convention: scipy.signal.correlation_lags returns lag such that
    # `correlate(a, b)` peaking at lag k means b's signal is aligned with
    # a when b is shifted *right* by -k samples — i.e. a positive k means
    # a leads b. We want `offset_s > 0` to mean *b is later than a*, so we
    # negate. See multi-camera-sync-spec.md §3.2 — "subtract offset_s
    # from b's timestamps to align them onto a's clock."
    offset_s = -fractional_lag / float(sample_rate_hz)

    # Confidence: normalized cross-correlation coefficient. Dividing the
    # raw peak by the product of the inputs' L2 norms maps the metric
    # into [0, 1] (for zero-meaned real signals) — perfectly aligned
    # identical signals give 1.0; uncorrelated noise gives ~1/sqrt(N).
    # The default threshold in `XcorrConfig.min_confidence` (0.3) sits
    # comfortably above the noise floor and below the values real
    # cross-camera muzzle blasts produce.
    a_norm = float(np.linalg.norm(a_bp))
    b_norm = float(np.linalg.norm(b_bp))
    denom = a_norm * b_norm
    confidence = float(mag[peak_idx]) / denom if denom > 0 else 0.0

    return AlignmentResult(
        offset_s=offset_s,
        sample_offset=-fractional_lag,
        confidence=confidence,
        peak_value=peak_value,
        confident=confidence >= cfg.min_confidence,
    )


def align_camera_pair(
    a_pcm: npt.NDArray[np.floating],
    b_pcm: npt.NDArray[np.floating],
    shot_times_in_a_s: list[float],
    sample_rate_hz: int,
    config: XcorrConfig | None = None,
) -> PairAlignment:
    """Align two cameras using cross-correlation across multiple shots.

    The caller provides shot times in `a`'s clock — typically from the
    audio shot detector run against `a`'s PCM. For each shot we extract
    `a`'s and `b`'s PCM around *the same nominal time* and run xcorr; if
    `b`'s clock is skewed by D relative to `a`'s, `b`'s blast lands D
    seconds away from the window center and the xcorr peak measures that
    skew.

    Why we don't take both cameras' detected shot times: if we extract
    each window around its own camera's detection, both blasts sit at
    the center of their respective windows and the xcorr peak is at
    lag 0 — the skew has been "subtracted out" by the shot detector
    before xcorr ever sees the signal. Taking shot times from one
    camera and reaching into the other at the same time is what
    preserves the skew for xcorr to measure.

    Returns the median per-shot offset and the per-shot detail. Median
    over confident-only shots is the canonical session offset; if every
    shot is unconfident the median falls back to all-shots so the
    caller still gets a number to inspect, but `confident_shot_count`
    will be 0 and the caller should fall back to MSYNC or the manual
    clap-board path per multi-camera-sync-spec §3.2.
    """
    cfg = config or XcorrConfig()
    _validate_pcm_pair(a_pcm, b_pcm, sample_rate_hz)
    if not shot_times_in_a_s:
        raise ValueError("need at least one shot time to align")

    # b's window needs to be wider than a's so the search range can
    # cover the full ±search_window_ms in b around each shot. We extract
    # the same window length from both because the xcorr math requires
    # length-matched inputs; the ±search_window_ms constraint is
    # enforced later by masking the xcorr output, not by the window
    # extraction.
    half_window = cfg.window_s / 2.0
    half_samples = int(round(half_window * sample_rate_hz))
    results: list[AlignmentResult] = []
    for t in shot_times_in_a_s:
        a_window = _extract_window(a_pcm, t, sample_rate_hz, half_samples)
        b_window = _extract_window(b_pcm, t, sample_rate_hz, half_samples)
        if a_window.size != b_window.size:
            # One of the shots landed too close to the start/end of the
            # PCM — truncate to the shorter of the two so the lengths
            # match. The trimmed window is still useful as long as the
            # blast is inside it.
            n = min(a_window.size, b_window.size)
            a_window = a_window[:n]
            b_window = b_window[:n]
        if a_window.size == 0:
            # Both windows degenerated to empty; nothing to correlate.
            results.append(AlignmentResult(0.0, 0.0, 0.0, 0.0, confident=False))
            continue
        results.append(cross_correlate_shot(a_window, b_window, sample_rate_hz, cfg))

    confident = [r for r in results if r.confident]
    pool = confident if confident else results
    median_offset = float(np.median([r.offset_s for r in pool]))
    return PairAlignment(
        median_offset_s=median_offset,
        confident_shot_count=len(confident),
        per_shot=tuple(results),
    )


def _extract_window(
    pcm: npt.NDArray[np.floating],
    t_s: float,
    sample_rate_hz: int,
    half_samples: int,
) -> npt.NDArray[np.floating]:
    """Pull `±half_samples` of PCM around `t_s`, clipped to the array bounds.

    No padding — if the shot is near the start or end of the recording,
    the window comes back shorter. `align_camera_pair` truncates the
    pair to the shorter window so the correlation stays length-matched.
    """
    center = int(round(t_s * sample_rate_hz))
    lo = max(0, center - half_samples)
    hi = min(pcm.size, center + half_samples)
    if hi <= lo:
        return pcm[0:0]
    return pcm[lo:hi]
