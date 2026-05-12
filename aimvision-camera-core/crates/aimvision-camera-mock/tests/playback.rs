//! Plays the canonical sample-session fixture and asserts the mock walks
//! the expected state-equivalent without hitting an `Err`.

use aimvision_camera_mock::{FaultScript, MockCamera};
use aimvision_camera_traits::{CameraControl, CameraEvent};

fn fixture_path(name: &str) -> std::path::PathBuf {
    let manifest =
        std::env::var("CARGO_MANIFEST_DIR").expect("cargo sets CARGO_MANIFEST_DIR for tests");
    let mut p = std::path::PathBuf::from(manifest);
    p.push("fixtures");
    p.push(name);
    p
}

#[tokio::test]
async fn sample_session_plays_clean() {
    let script = FaultScript::from_path(fixture_path("sample_session.yaml"))
        .expect("parse sample_session.yaml");
    assert!(
        script.shots.len() >= 50,
        "sample fixture should have 50+ shots"
    );
    assert!(script.faults.is_empty());

    let cam = MockCamera::new("cam_a", script);
    cam.connect().await.expect("connect");
    let _h = cam.start_recording().await.expect("start_recording");

    // Walk the session in 1-second slices for 1500 s (25 minutes covers the
    // first 4 stations of the sample). We don't go all 30 minutes here to
    // keep CI fast; the fixture itself is checked above.
    for _ in 0..1500 {
        cam.advance(1.0);
    }

    cam.stop_recording().await.expect("stop_recording");

    // Drain events. We expect at minimum: RecordingStarted, RecordingStopped,
    // and one FileReady. No ThermalShutdown, no BatteryCritical.
    let events = cam.drain_events();
    assert!(events.contains(&CameraEvent::RecordingStarted));
    assert!(events.contains(&CameraEvent::RecordingStopped));
    assert!(
        events
            .iter()
            .any(|e| matches!(e, CameraEvent::FileReady(_))),
        "expected FileReady event"
    );
    assert!(
        !events.contains(&CameraEvent::ThermalShutdown),
        "no thermal shutdown in clean session"
    );
}

#[tokio::test]
async fn capabilities_query_matches_mock_defaults() {
    let cam = MockCamera::new("cam_a", FaultScript::default());
    let caps = cam.query_capabilities();
    assert!(caps.live_preview);
    assert!(caps.hilight);
    assert!(caps.uvc);
    assert_eq!(caps.audio_sample_rate_hz, 48_000);
}
