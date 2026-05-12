//! Fault-injection tests. Inject `drop_wifi` at t=12.3s and assert that the
//! mock emits `WifiDown` then `WifiUp` after the configured duration.

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
async fn drop_wifi_at_12_3_emits_wifidown_then_wifiup() {
    let script =
        FaultScript::from_path(fixture_path("flaky_wifi.yaml")).expect("parse flaky_wifi.yaml");

    let cam = MockCamera::new("cam_a", script);
    cam.connect().await.expect("connect");
    cam.start_recording().await.expect("start");

    // Advance to t=12.0 — no fault yet.
    cam.advance(12.0);
    let mid_events = cam.drain_events();
    assert!(
        !mid_events
            .iter()
            .any(|e| matches!(e, CameraEvent::WifiDown)),
        "WifiDown should not fire before t=12.3"
    );

    // Advance past 12.3 — WifiDown should fire.
    cam.advance(0.5); // now at 12.5
    assert!(cam.is_wifi_down());
    let drop_events = cam.drain_events();
    assert!(
        drop_events
            .iter()
            .any(|e| matches!(e, CameraEvent::WifiDown)),
        "WifiDown event expected"
    );

    // Advance past 16.3 (12.3 + 4.0 duration). WifiUp should fire.
    cam.advance(4.0); // now at 16.5
    assert!(!cam.is_wifi_down());
    let up_events = cam.drain_events();
    assert!(
        up_events.iter().any(|e| matches!(e, CameraEvent::WifiUp)),
        "WifiUp event expected after outage duration"
    );
}

#[tokio::test]
async fn second_drop_wifi_window_recovers() {
    let script =
        FaultScript::from_path(fixture_path("flaky_wifi.yaml")).expect("parse flaky_wifi.yaml");
    let cam = MockCamera::new("cam_a", script);
    cam.connect().await.expect("connect");
    cam.start_recording().await.expect("start");

    // Walk the entire 30 s window in 1-s slices.
    for _ in 0..35 {
        cam.advance(1.0);
    }

    // Both drop and recovery for both windows must have been emitted.
    let evs = cam.drain_events();
    let down_count = evs
        .iter()
        .filter(|e| matches!(e, CameraEvent::WifiDown))
        .count();
    let up_count = evs
        .iter()
        .filter(|e| matches!(e, CameraEvent::WifiUp))
        .count();
    assert_eq!(down_count, 2, "expected two WifiDown events");
    assert_eq!(up_count, 2, "expected two WifiUp events");
}

#[tokio::test]
async fn thermal_throttle_emits_warning_and_battery_low() {
    let script = FaultScript::from_path(fixture_path("thermal_throttle.yaml"))
        .expect("parse thermal_throttle.yaml");
    let cam = MockCamera::new("cam_a", script);
    cam.connect().await.expect("connect");
    cam.start_recording().await.expect("start");

    for _ in 0..100 {
        cam.advance(1.0);
    }

    let evs = cam.drain_events();
    assert!(evs.iter().any(|e| matches!(
        e,
        CameraEvent::ThermalWarning(aimvision_camera_traits::ThermalState::Hot)
    )));
    assert!(evs.iter().any(|e| matches!(e, CameraEvent::BatteryLow(15))));
    assert!(evs
        .iter()
        .any(|e| matches!(e, CameraEvent::BleDisconnected)));
}
