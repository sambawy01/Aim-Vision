//! `MockCamera` — implements `CameraControl`, `CameraTransport`, `CameraMedia`,
//! `TimeSource` against a [`FaultScript`] fixture.
//!
//! This is the primary CI vehicle for the camera-core. Tests script a session,
//! advance the deterministic clock, and assert that the state machine and
//! command queue behave correctly.
//!
//! # Threading model
//!
//! The mock is `Send + Sync`. Internal state (event queue, buffers, current
//! state, faults-in-progress) lives behind a single `Mutex` because the
//! mock is never under high contention — tests advance time serially.
//! A real implementation would shard these into separate locks; that
//! optimisation is not justified here.

use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::Mutex;

use async_trait::async_trait;

use aimvision_camera_traits::{
    AudioChunk, CameraCapabilities, CameraControl, CameraError, CameraEvent, CameraMedia,
    CameraResult, CameraTransport, CaptureMode, FileId, Frame, FrameFormat, MediaSink, RawCommand,
    RawEvent, RecordingHandle, SettingId, SettingValue, ThermalState, TimeNs, TimeSource,
    TimeSourceKind, Transport,
};

use crate::clock::MockClock;
use crate::fault_script::{FaultKind, FaultScript, FaultSpec};

/// Mock camera. Cheaply cloneable — internal state is in `Arc<Mutex<...>>`.
#[derive(Clone)]
pub struct MockCamera {
    inner: Arc<Inner>,
}

struct Inner {
    id: String,
    capabilities: CameraCapabilities,
    clock: MockClock,
    state: Mutex<MockState>,
    script: FaultScript,
}

#[derive(Default)]
struct MockState {
    /// Whether `connect` has succeeded.
    connected: bool,
    /// Whether the camera is currently recording.
    recording: bool,
    /// Last advanced session-time, in seconds. Used to evaluate which faults
    /// have fired so we don't re-emit them.
    advanced_to_s: f64,
    /// Pending events ready for `receive_event`.
    pending_events: VecDeque<CameraEvent>,
    /// Pending preview frames.
    pending_frames: VecDeque<Frame>,
    /// Pending audio chunks.
    pending_audio: VecDeque<AudioChunk>,
    /// Frame counter for monotonic_seq.
    frame_seq: u64,
    /// Last-seen wall-clock for the transport diagnostic.
    last_seen_ns: TimeNs,
    /// Settings store (ID → value).
    settings: std::collections::HashMap<u16, SettingValue>,
    /// Currently in a `drop_wifi` outage; `Some(t_end_s)` means recovery happens
    /// at session-time `t_end_s`.
    wifi_outage_until_s: Option<f64>,
}

impl MockCamera {
    /// Construct a mock camera from a script and an identifier (used for
    /// multi-camera tests). The script is consumed; clone it on the caller
    /// side if you need to share between cameras.
    pub fn new(id: impl Into<String>, script: FaultScript) -> Self {
        let clock = MockClock::new(script.clock.skew_ms, script.clock.drift_ms_per_min);
        Self {
            inner: Arc::new(Inner {
                id: id.into(),
                capabilities: CameraCapabilities::mock(),
                clock,
                state: Mutex::new(MockState::default()),
                script,
            }),
        }
    }

    /// Read-only handle to the underlying clock for tests that need to drive
    /// time advancement explicitly.
    #[must_use]
    pub fn clock(&self) -> &MockClock {
        &self.inner.clock
    }

    /// Camera identifier.
    #[must_use]
    pub fn id(&self) -> &str {
        &self.inner.id
    }

    /// Advance simulated session time by `delta_s` seconds, firing any faults
    /// or shots that fall in the swept window.
    ///
    /// This is the deterministic test driver. Tests call `advance(0.1)` in a
    /// loop until the desired session length is reached, then assert on
    /// pending events / state.
    pub fn advance(&self, delta_s: f64) {
        let nanos = (delta_s * 1_000_000_000.0) as u64;
        self.inner.clock.advance(nanos);

        let mut st = self.lock();
        let from = st.advanced_to_s;
        let to = from + delta_s;
        st.advanced_to_s = to;
        st.last_seen_ns = self.inner.clock.now();

        // Wi-Fi outage recovery first, before evaluating new faults.
        if let Some(end_s) = st.wifi_outage_until_s {
            if to >= end_s {
                st.wifi_outage_until_s = None;
                st.pending_events.push_back(CameraEvent::WifiUp);
            }
        }

        // Faults whose `t` falls inside (from, to].
        let faults: Vec<FaultSpec> = self
            .inner
            .script
            .faults
            .iter()
            .filter(|f| f.t > from && f.t <= to)
            .cloned()
            .collect();
        for f in faults {
            Self::apply_fault(&mut st, &f);
        }

        // Synthesize a preview frame every ~33 ms (30 fps) and an audio
        // chunk every ~10 ms. We do this lazily — only if recording is on.
        // The test driver does its own audio synthesis for sync tests, so
        // we don't generate detailed audio here; the chunks are silence
        // unless the script's shots place transients.
        if st.recording {
            // One frame per advance call is sufficient for the tests we ship;
            // a real fixture player would interpolate more densely.
            let pts_ns = self.inner.clock.now();
            let seq = st.frame_seq;
            st.frame_seq = seq.saturating_add(1);
            st.pending_frames.push_back(Frame {
                handle_id: seq,
                format: FrameFormat::Nv12,
                width: 1920,
                height: 1080,
                pts_ns,
                monotonic_seq: seq,
            });
        }
    }

    fn apply_fault(st: &mut MockState, f: &FaultSpec) {
        match &f.kind {
            FaultKind::DropWifi { duration } => {
                st.wifi_outage_until_s = Some(f.t + duration);
                st.pending_events.push_back(CameraEvent::WifiDown);
            }
            FaultKind::BleDisconnect => {
                st.pending_events.push_back(CameraEvent::BleDisconnected);
            }
            FaultKind::ThermalWarn => {
                st.pending_events
                    .push_back(CameraEvent::ThermalWarning(ThermalState::Hot));
            }
            FaultKind::BatteryLow { level } => {
                st.pending_events.push_back(CameraEvent::BatteryLow(*level));
            }
            FaultKind::HilightInserted => {
                let ts = (f.t * 1_000_000_000.0) as u64;
                st.pending_events
                    .push_back(CameraEvent::HilightInserted(ts));
            }
            FaultKind::Command500 => {
                // Surfaces as a vendor event — the command queue tests
                // exercise watchdog timeouts via a separate path.
                st.pending_events
                    .push_back(CameraEvent::Vendor(aimvision_camera_traits::VendorEvent {
                        vendor: "mock".into(),
                        kind: "command_500".into(),
                        payload_json: "{}".into(),
                    }));
            }
            FaultKind::FileChunkDropped => {
                st.pending_events
                    .push_back(CameraEvent::Vendor(aimvision_camera_traits::VendorEvent {
                        vendor: "mock".into(),
                        kind: "file_chunk_dropped".into(),
                        payload_json: "{}".into(),
                    }));
            }
        }
    }

    /// Push an audio chunk into the audio buffer. Used by sync tests to
    /// inject synthesized muzzle blasts.
    pub fn push_audio_chunk(&self, chunk: AudioChunk) {
        let mut st = self.lock();
        st.pending_audio.push_back(chunk);
    }

    /// Drain all pending events. Tests typically do this after advancing time.
    pub fn drain_events(&self) -> Vec<CameraEvent> {
        let mut st = self.lock();
        st.pending_events.drain(..).collect()
    }

    /// Returns `true` if the camera is currently in a Wi-Fi outage window.
    #[must_use]
    pub fn is_wifi_down(&self) -> bool {
        self.lock().wifi_outage_until_s.is_some()
    }

    /// Returns the script the mock is replaying. Tests use this to sanity-
    /// check fixture parsing.
    #[must_use]
    pub fn script(&self) -> &FaultScript {
        &self.inner.script
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, MockState> {
        self.inner
            .state
            .lock()
            .expect("mock camera state mutex poisoned")
    }
}

// -- TimeSource ---------------------------------------------------------------

impl TimeSource for MockCamera {
    fn now(&self) -> TimeNs {
        self.inner.clock.now()
    }
    fn kind(&self) -> TimeSourceKind {
        self.inner.clock.kind()
    }
}

// -- CameraControl ------------------------------------------------------------

#[async_trait]
impl CameraControl for MockCamera {
    async fn connect(&self) -> CameraResult<()> {
        let mut st = self.lock();
        st.connected = true;
        st.last_seen_ns = self.inner.clock.now();
        Ok(())
    }

    async fn disconnect(&self) -> CameraResult<()> {
        let mut st = self.lock();
        st.connected = false;
        st.recording = false;
        Ok(())
    }

    async fn start_recording(&self) -> CameraResult<RecordingHandle> {
        let mut st = self.lock();
        if !st.connected {
            return Err(CameraError::Vendor(
                "cannot start recording before connect".into(),
            ));
        }
        st.recording = true;
        st.pending_events.push_back(CameraEvent::RecordingStarted);
        Ok(RecordingHandle::new())
    }

    async fn stop_recording(&self) -> CameraResult<()> {
        let mut st = self.lock();
        st.recording = false;
        st.pending_events.push_back(CameraEvent::RecordingStopped);
        // Emit a synthetic FileReady so file-transfer tests have something
        // to chew on.
        st.pending_events
            .push_back(CameraEvent::FileReady(FileId::new_v4()));
        Ok(())
    }

    async fn pause(&self) -> CameraResult<()> {
        let mut st = self.lock();
        st.recording = false;
        Ok(())
    }

    async fn resume(&self) -> CameraResult<()> {
        let mut st = self.lock();
        st.recording = true;
        Ok(())
    }

    async fn insert_hilight(&self, at: TimeNs) -> CameraResult<()> {
        let mut st = self.lock();
        st.pending_events.push_back(CameraEvent::HilightInserted(at));
        Ok(())
    }

    async fn set_setting(&self, id: SettingId, value: SettingValue) -> CameraResult<()> {
        let mut st = self.lock();
        st.settings.insert(id.0, value);
        Ok(())
    }

    async fn get_setting(&self, id: SettingId) -> CameraResult<SettingValue> {
        let st = self.lock();
        st.settings
            .get(&id.0)
            .cloned()
            .ok_or(CameraError::Unsupported("setting not present"))
    }

    fn query_capabilities(&self) -> &CameraCapabilities {
        &self.inner.capabilities
    }
}

// -- CameraTransport ----------------------------------------------------------

#[async_trait]
impl CameraTransport for MockCamera {
    async fn send_command(&self, _cmd: RawCommand) -> CameraResult<RawEvent> {
        // The mock pretends every command succeeds with a single-byte ack
        // (0x00). The command queue tests inject watchdog timeouts at their
        // own layer.
        Ok(RawEvent(vec![0x00]))
    }

    async fn receive_event(&self) -> CameraResult<Option<RawEvent>> {
        // The high-level events live in `pending_events`; the raw transport
        // layer just signals "we have stuff" so the consumer can promote
        // it. Returning `None` indicates "graceful idle".
        let st = self.lock();
        if st.pending_events.is_empty() {
            Ok(None)
        } else {
            // Encoding raw events is out of scope for the mock — return
            // a sentinel byte indicating "drain pending_events via the
            // CameraControl-side API".
            Ok(Some(RawEvent(vec![0xff])))
        }
    }

    fn transport_kind(&self) -> Transport {
        Transport::WifiHttp
    }

    fn last_seen(&self) -> TimeNs {
        self.lock().last_seen_ns
    }
}

// -- CameraMedia --------------------------------------------------------------

#[async_trait]
impl CameraMedia for MockCamera {
    fn poll_preview_frame(&self) -> Option<Frame> {
        let mut st = self.lock();
        st.pending_frames.pop_front()
    }

    fn poll_audio_chunk(&self) -> Option<AudioChunk> {
        let mut st = self.lock();
        st.pending_audio.pop_front()
    }

    async fn download_file(
        &self,
        _file_id: FileId,
        sink: &mut dyn MediaSink,
    ) -> CameraResult<()> {
        // Synthesize a small file for tests.
        const PAYLOAD: &[u8] = b"FAKE-MP4-FAKE-MP4-FAKE-MP4-FAKE-MP4";
        sink.write_chunk(PAYLOAD).await?;
        sink.finalize().await?;
        Ok(())
    }
}

/// Mode helper used by tests that want to explicitly switch capture modes
/// before recording. The mock tracks this under setting ID `0xFFFF`.
#[must_use]
pub fn capture_mode_setting_id() -> SettingId {
    SettingId(0xFFFF)
}

/// Tests use this to set capture mode in a roundtrip-safe way.
pub async fn set_capture_mode(cam: &MockCamera, mode: CaptureMode) -> CameraResult<()> {
    let v = match mode {
        CaptureMode::Video => SettingValue::U8(0),
        CaptureMode::Webcam => SettingValue::U8(1),
        CaptureMode::Photo => SettingValue::U8(2),
    };
    cam.set_setting(capture_mode_setting_id(), v).await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_script() -> FaultScript {
        FaultScript::default()
    }

    #[tokio::test]
    async fn connect_then_record_emits_recording_started() {
        let cam = MockCamera::new("cam_a", empty_script());
        cam.connect().await.expect("connect");
        let _h = cam.start_recording().await.expect("start");
        let events = cam.drain_events();
        assert!(events.contains(&CameraEvent::RecordingStarted));
    }

    #[tokio::test]
    async fn cannot_record_without_connect() {
        let cam = MockCamera::new("cam_a", empty_script());
        let r = cam.start_recording().await;
        assert!(r.is_err());
    }

    #[tokio::test]
    async fn capabilities_match_mock_default() {
        let cam = MockCamera::new("cam_a", empty_script());
        let caps = cam.query_capabilities();
        assert!(caps.live_preview);
        assert!(caps.hilight);
    }

    #[tokio::test]
    async fn set_get_setting_roundtrip() {
        let cam = MockCamera::new("cam_a", empty_script());
        let id = SettingId(42);
        cam.set_setting(id, SettingValue::U16(1080))
            .await
            .expect("set");
        let v = cam.get_setting(id).await.expect("get");
        assert_eq!(v, SettingValue::U16(1080));
    }
}
