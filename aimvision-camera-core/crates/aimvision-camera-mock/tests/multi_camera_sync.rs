//! Two-mock-camera sync test.
//!
//! Per `docs/multi-camera-sync-spec.md` §8, the synthetic 2-camera rig must
//! recover per-shot offsets to within ±1 ms of ground truth, using audio
//! cross-correlation on a synthesized muzzle-blast transient.
//!
//! This test wires up two `MockCamera`s with deliberate skew (15 ms) and
//! drift (2 ms/min), pushes synchronized synthetic muzzle blasts into both
//! audio buffers (offset by exactly the skew amount), runs a naive
//! cross-correlation peak search, and asserts the recovered offset is
//! within ±1 ms of ground truth.

use aimvision_camera_mock::{FaultScript, MockCamera};
use aimvision_camera_traits::{AudioChunk, CameraMedia};

const SAMPLE_RATE: u32 = 48_000;

/// Build a muzzle-blast PCM impulse: short rise, sharp peak, exponential decay.
/// Total length: ~50 ms = 2400 samples at 48 kHz.
fn synthesize_muzzle_blast() -> Vec<i16> {
    let total = 2400usize;
    let peak_at = 50usize; // ~1 ms in
    let mut out = Vec::with_capacity(total);
    for i in 0..total {
        let v: f32 = if i < peak_at {
            // Linear rise to peak.
            (i as f32 / peak_at as f32) * 0.95
        } else {
            // Exponential decay; tau = 200 samples (~4 ms).
            0.95 * f32::exp(-((i - peak_at) as f32) / 200.0)
        };
        // Saturate to i16.
        let s = (v * f32::from(i16::MAX)) as i16;
        out.push(s);
    }
    out
}

/// Synthesize an audio chunk with the muzzle blast embedded at `embed_offset_samples`
/// inside a `chunk_len_samples`-sample window of background silence.
fn make_chunk(
    chunk_len_samples: usize,
    embed_offset_samples: usize,
    blast: &[i16],
    start_ts_ns: u64,
) -> AudioChunk {
    let mut samples = vec![0i16; chunk_len_samples];
    for (i, s) in blast.iter().enumerate() {
        let pos = embed_offset_samples + i;
        if pos < chunk_len_samples {
            samples[pos] = *s;
        }
    }
    AudioChunk {
        samples,
        sample_rate_hz: SAMPLE_RATE,
        channels: 1,
        start_ts_ns,
    }
}

/// Naive normalised cross-correlation peak search.
///
/// Returns the integer-sample lag of `b` relative to `a` that maximises
/// `sum(a[i] * b[i + lag])`. Searched lags: `-search_radius..=search_radius`.
///
/// We use i64 accumulators to avoid overflow on the i16-product sums.
fn xcorr_peak_lag(a: &[i16], b: &[i16], search_radius: i32) -> i32 {
    let mut best_lag: i32 = 0;
    let mut best_score: i64 = i64::MIN;
    let n = a.len().min(b.len()) as i32;
    for lag in -search_radius..=search_radius {
        let mut score: i64 = 0;
        // For each i, take a[i] * b[i + lag] when both indices are valid.
        let i_start = lag.max(0);
        let i_end = (n + lag.min(0)).min(n);
        if i_end <= i_start {
            continue;
        }
        for i in i_start..i_end {
            let ai = a[i as usize] as i64;
            let bi = b[(i - lag) as usize] as i64;
            score += ai * bi;
        }
        if score > best_score {
            best_score = score;
            best_lag = lag;
        }
    }
    best_lag
}

#[tokio::test]
async fn xcorr_recovers_known_skew_within_one_ms() {
    // Per docs/multi-camera-sync-spec.md §3.2 the audio cross-correlation
    // step recovers the relative offset between two cameras using a
    // shared muzzle-blast transient. This test wires up two mock cameras
    // — one with zero skew, one whose chunk has the blast 720 samples
    // (= 15 ms at 48 kHz) shifted relative to the first — and asserts
    // the xcorr peak picks up that 15 ms offset within the ±1 ms budget.
    //
    // We script the `MockClock` skew on cam_b for completeness (so the
    // mock's `TimeSource::now()` reports a 15 ms-ahead clock matching the
    // audio offset), but the xcorr math operates on the PCM directly.
    let script_a = FaultScript {
        clock: aimvision_camera_mock::ClockSpec {
            skew_ms: 0.0,
            drift_ms_per_min: 0.0,
        },
        ..Default::default()
    };
    let script_b = FaultScript {
        clock: aimvision_camera_mock::ClockSpec {
            skew_ms: 15.0,
            drift_ms_per_min: 2.0,
        },
        ..Default::default()
    };

    let cam_a = MockCamera::new("cam_a", script_a);
    let cam_b = MockCamera::new("cam_b", script_b);

    // Build a 100 ms (4800-sample) chunk.
    let chunk_len = 4800usize;
    let blast = synthesize_muzzle_blast();

    // Embed the same physical blast in two chunks with a known 720-sample
    // (= 15 ms) offset between them. cam_a places the blast at sample 1000;
    // cam_b's chunk has it at sample 1720 (delayed by 15 ms).
    let embed_a = 1000usize;
    let embed_b = embed_a + 720; // 1720

    let chunk_a = make_chunk(chunk_len, embed_a, &blast, 0);
    let chunk_b = make_chunk(chunk_len, embed_b, &blast, 0);

    cam_a.push_audio_chunk(chunk_a);
    cam_b.push_audio_chunk(chunk_b);

    // Pull the chunks back via the trait.
    let pulled_a = cam_a.poll_audio_chunk().expect("chunk A");
    let pulled_b = cam_b.poll_audio_chunk().expect("chunk B");

    // Run xcorr with a ±50 ms search window (2400 samples).
    let lag = xcorr_peak_lag(&pulled_a.samples, &pulled_b.samples, 2400);

    // Lag in samples → ms. With the convention used by xcorr_peak_lag
    // (`score(k) = sum a[i] * b[i - k]`), if cam_b is delayed relative to
    // cam_a by 720 samples (b[j] = a[j - 720]), the peak is at k = -720.
    let lag_ms = lag as f64 / f64::from(SAMPLE_RATE) * 1_000.0;
    let expected_ms = -15.0;
    let err_ms = (lag_ms - expected_ms).abs();
    assert!(
        err_ms < 1.0,
        "xcorr recovered lag {lag_ms:.3} ms; expected {expected_ms:.3} ms; \
         error {err_ms:.3} ms exceeds ±1 ms budget"
    );
}

#[tokio::test]
async fn xcorr_with_zero_skew_returns_zero_lag() {
    // Sanity check: identical chunks should xcorr to zero lag.
    let blast = synthesize_muzzle_blast();
    let chunk_len = 4800usize;
    let chunk_a = make_chunk(chunk_len, 1000, &blast, 0);
    let chunk_b = make_chunk(chunk_len, 1000, &blast, 0);
    let lag = xcorr_peak_lag(&chunk_a.samples, &chunk_b.samples, 1000);
    assert_eq!(lag, 0, "identical chunks should peak at lag=0");
}

#[tokio::test]
async fn drift_compensation_within_two_ms_over_one_minute() {
    // Camera B drifts at 2 ms/min. After 60 seconds of session time the
    // clock should report ~2 ms more than session_ns. Per spec §3.3 we
    // re-anchor with audio every shot so accumulated drift in the
    // interpolated regions is bounded; this test is a smaller assertion:
    // the underlying clock model does what we say it does.
    use aimvision_camera_traits::TimeSource;

    let cam_b = MockCamera::new(
        "cam_b",
        FaultScript {
            clock: aimvision_camera_mock::ClockSpec {
                skew_ms: 0.0,
                drift_ms_per_min: 2.0,
            },
            ..Default::default()
        },
    );

    cam_b.advance(60.0); // 60 s of session time
    let now = TimeSource::now(&cam_b);
    let drift_ns = now as i64 - 60_000_000_000_i64;
    let drift_ms = drift_ns as f64 / 1_000_000.0;

    assert!(
        (drift_ms - 2.0).abs() < 0.05,
        "drift over 1 min was {drift_ms:.3} ms; expected ~2.0 ms (±0.05)"
    );
}
