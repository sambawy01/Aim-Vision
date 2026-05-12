//! YAML fault-script grammar.
//!
//! Parses fixtures of the shape:
//!
//! ```yaml
//! shots:
//!   - { t: 1.2, station: 1 }
//!   - { t: 4.5, station: 1 }
//! faults:
//!   - { t: 12.3, kind: drop_wifi, duration: 4.0 }
//!   - { t: 18.0, kind: ble_disconnect }
//!   - { t: 22.0, kind: thermal_warn }
//!   - { t: 45.0, kind: battery_low, level: 15 }
//! clock:
//!   skew_ms: 0
//!   drift_ms_per_min: 0
//! ```
//!
//! See `docs/camera-integration-spec.md` §12.1 for the canonical grammar.

use std::path::Path;

use serde::{Deserialize, Serialize};

use aimvision_camera_traits::CameraResult;

/// One shot (gunshot event) on a fixture timeline.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ShotSpec {
    /// Time in seconds since session start.
    pub t: f64,
    /// Station number (1-indexed).
    #[serde(default = "default_station")]
    pub station: u8,
    /// Synthesized muzzle-blast peak amplitude (0.0..=1.0). Tests that run
    /// audio cross-correlation use this to build the synthetic PCM.
    #[serde(default = "default_amplitude")]
    pub audio_amplitude: f32,
}

fn default_station() -> u8 {
    1
}
fn default_amplitude() -> f32 {
    0.85
}

/// Fault-injection event.
///
/// `kind` is a tagged enum on the wire so YAML can be authored as
/// `{ kind: drop_wifi, duration: 4.0 }`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FaultSpec {
    /// Time in seconds since session start when the fault is injected.
    pub t: f64,
    /// Kind of fault.
    #[serde(flatten)]
    pub kind: FaultKind,
}

/// All currently-supported fault kinds. `non_exhaustive` so the grammar
/// can grow without breaking existing fixtures.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
#[non_exhaustive]
pub enum FaultKind {
    /// Wi-Fi drops for `duration` seconds, then reconnects.
    DropWifi {
        /// Duration of the outage in seconds.
        duration: f64,
    },
    /// BLE link drops once. Recovery is handled by the state machine.
    BleDisconnect,
    /// Thermal warning escalates to `Hot`.
    ThermalWarn,
    /// Battery drops to `level` percent.
    BatteryLow {
        /// Battery percent remaining (0..=100).
        level: u8,
    },
    /// Hilight tag inserted at the script's `t` timestamp.
    HilightInserted,
    /// HTTP 500 from the camera (single occurrence).
    #[serde(rename = "command_500")]
    Command500,
    /// One file-download chunk drops mid-transfer.
    FileChunkDropped,
}

/// Clock parameters. Empty / missing block means "no skew, no drift".
#[derive(Copy, Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ClockSpec {
    /// Constant skew, in milliseconds.
    #[serde(default)]
    pub skew_ms: f64,
    /// Linear drift, in milliseconds per minute. 2.0 means the camera clock
    /// is 2 ms ahead of session time after 1 minute.
    #[serde(default)]
    pub drift_ms_per_min: f64,
}

impl Default for ClockSpec {
    fn default() -> Self {
        Self {
            skew_ms: 0.0,
            drift_ms_per_min: 0.0,
        }
    }
}

/// Complete fault script, parsed from a fixture file.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct FaultScript {
    /// Shot timeline.
    #[serde(default)]
    pub shots: Vec<ShotSpec>,
    /// Fault timeline.
    #[serde(default)]
    pub faults: Vec<FaultSpec>,
    /// Clock parameters.
    #[serde(default)]
    pub clock: ClockSpec,
}

impl FaultScript {
    /// Parse a fault script from a YAML string.
    pub fn from_yaml_str(s: &str) -> CameraResult<Self> {
        let parsed: Self = serde_yaml::from_str(s)?;
        Ok(parsed)
    }

    /// Parse a fault script from a file on disk.
    pub fn from_path(path: impl AsRef<Path>) -> CameraResult<Self> {
        let bytes =
            std::fs::read_to_string(path).map_err(aimvision_camera_traits::CameraError::from)?;
        Self::from_yaml_str(&bytes)
    }

    /// All faults whose `t` falls in `[t_start_s, t_end_s)`.
    pub fn faults_in_window(&self, t_start_s: f64, t_end_s: f64) -> Vec<&FaultSpec> {
        self.faults
            .iter()
            .filter(|f| f.t >= t_start_s && f.t < t_end_s)
            .collect()
    }

    /// All shots whose `t` falls in `[t_start_s, t_end_s)`.
    pub fn shots_in_window(&self, t_start_s: f64, t_end_s: f64) -> Vec<&ShotSpec> {
        self.shots
            .iter()
            .filter(|s| s.t >= t_start_s && s.t < t_end_s)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
shots:
  - { t: 1.2, station: 1 }
  - { t: 4.5, station: 1 }
faults:
  - { t: 12.3, kind: drop_wifi, duration: 4.0 }
  - { t: 18.0, kind: ble_disconnect }
  - { t: 22.0, kind: thermal_warn }
  - { t: 45.0, kind: battery_low, level: 15 }
clock:
  skew_ms: 0
  drift_ms_per_min: 0
"#;

    #[test]
    fn parses_canonical_sample() {
        let s = FaultScript::from_yaml_str(SAMPLE).expect("parse");
        assert_eq!(s.shots.len(), 2);
        assert_eq!(s.faults.len(), 4);
        assert_eq!(s.clock.skew_ms, 0.0);

        match &s.faults[0].kind {
            FaultKind::DropWifi { duration } => assert!((duration - 4.0).abs() < 1e-9),
            other => panic!("expected DropWifi, got {other:?}"),
        }
        match &s.faults[3].kind {
            FaultKind::BatteryLow { level } => assert_eq!(*level, 15),
            other => panic!("expected BatteryLow, got {other:?}"),
        }
    }

    #[test]
    fn missing_clock_block_defaults() {
        let yaml = r#"
shots:
  - { t: 1.0, station: 1 }
"#;
        let s = FaultScript::from_yaml_str(yaml).expect("parse");
        assert_eq!(s.clock, ClockSpec::default());
        assert!(s.faults.is_empty());
    }

    #[test]
    fn empty_yaml_is_valid_empty_script() {
        let s = FaultScript::from_yaml_str("{}").expect("parse");
        assert!(s.shots.is_empty());
        assert!(s.faults.is_empty());
    }

    #[test]
    fn faults_in_window_filters_correctly() {
        let s = FaultScript::from_yaml_str(SAMPLE).expect("parse");
        let in_window = s.faults_in_window(10.0, 20.0);
        assert_eq!(in_window.len(), 2); // drop_wifi @ 12.3, ble_disconnect @ 18.0
    }

    #[test]
    fn unknown_fault_kind_fails_to_parse() {
        let yaml = r#"
faults:
  - { t: 1.0, kind: nuclear_meltdown }
"#;
        let result = FaultScript::from_yaml_str(yaml);
        assert!(result.is_err(), "expected parse error for unknown kind");
    }
}
