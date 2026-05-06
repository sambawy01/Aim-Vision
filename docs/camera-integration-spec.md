# AIMVISION Camera Integration Specification

**Status:** Draft v1.0
**Owner:** Embedded Firmware Engineer
**Date:** 2026-05-06
**Related:** `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/10-performance-benchmarker.md`, `docs/reviews/03-software-architect.md`, ADR-0003 (Camera trait split)

This document is the contract between the Rust core and every camera surface AIMVISION will ship against. It is opinionated, version-pinned, and assumes outdoor Egyptian range conditions (35–45 °C, dust, 2.4 GHz congestion). Anything labelled "P0" is non-negotiable for V1; "V1.5" is the next minor; "V2" is the custom-hardware roadmap.

---

## 1. Open GoPro Reality on Hero 13

The Hero 13 implements the Open GoPro 2.0 specification. There are five protocol surfaces; we use four and ignore the fifth.

### 1.1 BLE GATT services

| UUID (16-bit prefix) | Service | What we call into |
|---|---|---|
| `0xFEA6` | GoPro Service container | discovery only |
| Command (`b5f90072-…`) | settings/cmd writes | start/stop, mode, hilight, presets, **Unpair** |
| Setting (`b5f90074-…`) | live settings push | resolution, FPS, lens, audio, AP band |
| Query (`b5f90076-…`) | poll status registers | thermal, battery, encoding state, SD |
| WiFi-AP (`b5f90002-…`) | SSID/PW + 2.4/5 GHz band switch | new on Hero 13 |

The "Unpair" command is the only reliable way to clear the camera's bonded-peer cache. We MUST issue it any time the BLE bond fails on the third reconnect attempt — see §4.

### 1.2 HTTP API on port 8080

Reachable only after the phone has joined the camera AP. Endpoints we use:

- `GET /gopro/camera/state` — full status block
- `GET /gopro/camera/presets/load?id=…` — preset switch (atomic)
- `GET /gopro/media/list` — JSON tree of SD card contents
- `GET /gopro/media/download/<path>` — raw MP4 over chunked transfer
- `GET /gopro/media/hilight?ts_ms=…` — best-effort tag insertion
- `GET /gopro/camera/control/start` / `/stop` — recording

The HTTP server has **no formal rate limit but serializes commands**. Two overlapping requests return HTTP 500 or hang the camera state machine for ~3 s. See §5 for the mandatory single-in-flight queue.

### 1.3 UDP MPEG-TS preview on port 8554

After issuing `GET /gopro/camera/stream/start`, the camera multicasts an H.264-in-MPEG-TS stream to the phone's address on port 8554, ~480p/30fps, ~2.5 Mbit/s. **Documented latency floor is 1.0–1.5 s; observed floor on Hero 13 is ~1.2 s with a clean 5 GHz link, 2.0–2.5 s on 2.4 GHz under congestion.** This floor is in the camera's encoder + Wi-Fi stack and **cannot be reduced** by any client-side change. See `docs/reviews/10-performance-benchmarker.md` §"Critical Performance Risk" — we publicly state p50 ≤ 2.5 s on Wi-Fi, not 1 s.

### 1.4 USB-C UVC mode at 1080p

Hero 13 with USB-C in "Webcam Mode" exposes a standard UVC video device + UAC audio device at 1080p30 with **measured glass-to-glass latency 200–400 ms**. This is the only credible <1 s path. **Federation tier is USB-C UVC tethered, P0** — not "P1 investigate" as the original sprint plan had it (per perf review).

### 1.5 What we ignore

The "Cohn" cloud-relay tunnel and the legacy WoL Wi-Fi management surface — both are stock-app crutches and add nothing for our use case.

### 1.6 Hero 13 vs. predecessors

The single new capability we depend on is **dual-band AP control over BLE** (toggle 2.4 ↔ 5 GHz without joining the AP first). Everything else is parity with Hero 12. We will not assume parity with Hero 11 — setting IDs renumbered between Hero 11 v01.20 and v02.00 and we have been bitten before.

---

## 2. Transport Selection Matrix

Tier-driven defaults, all overridable via settings panel for power users.

| Tier | Primary | Fallback | Notes |
|---|---|---|---|
| **Solo** | Wi-Fi 5 GHz, **forced** via BLE band-switch on connect | Wi-Fi 2.4 GHz with persistent **"Quality Degraded"** banner in UI | Latency budget honest at 2.5 s p50 |
| **Club** | Wi-Fi 5 GHz | Recommend operator-station USB tether to phone (Lightning-to-USB-C cam adapter) when 2.4 GHz fallback triggers; show a how-to card | Range is shorter on 5 GHz — phone within ~10 m of camera |
| **Federation** | **USB-C UVC tethered, P0** | Wi-Fi 5 GHz only as graceful degradation; the federation tier publicly advertises <1 s feed latency and that requires wired | Wired tether implies powered USB hub at operator station — see §11 |

The transport is selected by `CameraTransport::negotiate(tier, capabilities)` at session start. Once negotiated, the transport is sticky for the session — silent fallback during a string would corrupt timing analytics.

---

## 3. Connection State Machine

Implemented in the Rust core (`crate aimvision-camera-core`), exposed across UniFFI as a `CameraEvent::StateChanged(CameraState)`. States are exhaustive; transitions are explicit; recovery is per-failure-mode, not generic retry.

### 3.1 States

```
Disconnected         — no BLE, no Wi-Fi, no USB
Discovering          — BLE central scanning, advertisement filtered by GoPro service UUID
BlePairing           — bond initiation in progress; up to 3 attempts
BleConnected         — GATT subscriptions live; can issue settings commands
WifiActivating       — band selected, AP credentials read, phone OS join initiated
WifiConnected        — port 8080 reachable, /state returned 200
ReadyForRecording    — preset loaded, preview optional, audio routed
Recording            — REC indicator confirmed, hilight queue armed
RecordingPaused      — recording explicitly paused (stock firmware: no real pause; emulated as stop+restart with chapter merge)
FileTransferring     — post-session: enumerating + downloading
Disconnecting        — graceful teardown: stop preview, leave AP, BLE keepalive only
Errored(ErrorKind)   — terminal-ish; all recovery paths route through this with explicit kind
```

### 3.2 Transition table (edges)

| From | Trigger | To |
|---|---|---|
| Disconnected | `start_session()` | Discovering |
| Discovering | adv match | BlePairing |
| Discovering | 8 s timeout | Errored(NoCamera) |
| BlePairing | bond OK | BleConnected |
| BlePairing | bond rejected (3×) | Errored(BondCacheStale) — see §4 |
| BleConnected | tier=federation | WifiActivating(skip) → USB-C path instead |
| BleConnected | `enable_wifi()` ack | WifiActivating |
| WifiActivating | OS-join success | WifiConnected |
| WifiActivating | OS-join timeout 12 s | Errored(WifiJoinFailed) |
| WifiConnected | `/state` 200 | ReadyForRecording |
| ReadyForRecording | `record_start()` ack | Recording |
| Recording | iOS background event | RecordingPaused (BLE keepalive only) |
| Recording | shutdown / SD full | Errored(RecordingTerminated) |
| Recording | `record_stop()` ack | FileTransferring |
| FileTransferring | last file complete | Disconnecting |
| Errored(*) | `recover()` | back to Discovering or BleConnected per kind |

### 3.3 Recovery for known failure modes

Generic retry is forbidden. Each failure mode has a dedicated recovery routine:

- **iOS backgrounding tears Wi-Fi.** When `UIApplication.willResignActive` fires, we proactively `Disconnecting → BleConnected` and keep BLE alive (iOS allows BLE central in background under the bluetooth-central UIBackgroundMode). On `willEnterForeground`, transition `BleConnected → WifiActivating`. The recording continues on the camera throughout — we are not the recorder, we are the controller.
- **Android Doze kills socket.** Foreground Service with `dataSync` + `connectedDevice` types declared. Even so, Doze can kill our TCP socket; we detect via TCP-keepalive (60 s probe, 3 retries) and re-enter `WifiActivating` without dropping BLE.
- **BLE bond cache.** See §4.
- **HTTP 500 from concurrent commands.** Caught by command queue (§5), surfaced as a transient; one retry after 250 ms. If it repeats, queue is paused and a `Errored(CameraStateMachineHang)` is emitted — recovery is a BLE-level reset (`/gopro/camera/control/wired_usb` toggle, then re-enter ReadyForRecording).

### 3.4 Forbidden transitions

`Recording → Disconnected` may never be silent. If we lose all transports while the camera is recording, we MUST hold the user-visible session open, keep retrying BLE for 90 s, and on success issue a hilight tag with the gap timestamp so post-session reconciliation can flag the dropout.

---

## 4. Bond + Pairing Recovery

The Hero 13 bond is stored on the camera AND on the phone OS. A "forget on both ends" recovery path is mandatory; without it, users hit a wall after switching phones, factory-resetting the camera, or sharing a camera between Solo accounts.

### 4.1 Camera-side: Unpair via BLE

Write to the Command service GATT char (`0xb5f90072` family), opcode for "Unpair All" (single byte 0x09 in current firmware; matrix-tested per §9). This clears the camera's bonded-peer list immediately — the camera reboots its BLE stack but keeps recording state intact.

### 4.2 iOS side: CoreBluetooth bond cache invalidation

CoreBluetooth caches CBPeripheral identifiers indefinitely. We:

1. Call `CBCentralManager.cancelPeripheralConnection`.
2. **Do not** call `retrievePeripherals(withIdentifiers:)` for the stale UUID for at least one full app lifecycle.
3. Force a fresh scan with `scanForPeripherals(withServices:)` + `CBCentralManagerScanOptionAllowDuplicatesKey: false`.
4. The user is shown the system Bluetooth Settings deep link (`App-Prefs:Bluetooth`) and asked to "Forget This Device" if the second pairing attempt also fails — iOS Settings is the only API that fully clears the bond.

### 4.3 Android side: pairing retry without bond

Android exposes `BluetoothDevice.removeBond()` via reflection on most OEMs (Samsung gates it on Knox). We:

1. `bluetoothDevice.removeBond()` reflectively, swallow SecurityException.
2. Wait for `ACTION_BOND_STATE_CHANGED` → `BOND_NONE`.
3. Re-pair with `createBond()` and `BluetoothDevice.TRANSPORT_LE` explicit.
4. If `removeBond()` is blocked, we fall back to telling the user to clear pairing in Settings and document this is a Samsung Knox limitation.

### 4.4 The full recovery flow

```
BlePairing fails (×3) →
  show modal "Camera was previously paired with another device" →
  user confirms "Reset" →
  send Unpair via current GATT (if any) →
  invalidate phone-side bond →
  re-enter Discovering with a fresh BLE central manager
```

Modal copy approved in design review (V1 spec): never blame the user, never blame "Bluetooth," name the camera and the device.

---

## 5. Command Queue

The Hero 13 HTTP server hangs its state machine on overlapping commands. The Rust core implements a single-in-flight FIFO queue around the HTTP client.

### 5.1 Properties

- **In-flight depth:** exactly 1.
- **Per-command watchdog:** 2 s (start/stop), 5 s (preset load), 30 s (file download chunk).
- **Retry policy:** exponential backoff at 250 ms, 500 ms, 1 s — capped at 3 attempts.
- **Idempotency key:** every command carries a UUID; the response handler de-duplicates if the camera replies twice for one logical request (observed during BLE-link flap).
- **Queue depth cap:** 16 pending commands; overflow drops oldest non-critical (settings poll) first, never start/stop.
- **Critical commands jump:** `record_stop` and `Unpair` may bypass the queue and pre-empt the in-flight command (we issue the new command and discard the prior response).

### 5.2 Why this prevents the state-machine hang

Empirically: two overlapping `presets/load` commands within 800 ms of each other take the camera into a state where `/state` returns 200 but `record_start` returns 500 indefinitely until reboot. With a 2 s watchdog and single in-flight, this is unreachable.

---

## 6. Live Preview Consumption

The preview path is independent of the recording lifecycle. It exists only for operator UX, never for analytics ground truth (analytics run on the recorded MP4 post-session).

### 6.1 Pipeline

```
UDP MPEG-TS (port 8554)
  → demux (TS PID filter, video PID only)
  → H.264 elementary stream
  → hardware decode (VideoToolbox iOS / MediaCodec Android, NEVER software)
  → YUV/NV12 surface, zero-copy where possible
  → native Skia/Metal compositor
  → keypoint overlay from JSI bridge (per architect review §"3 High-Leverage Redesigns")
```

**Software H.264 decode is forbidden** — burns 35%/hr of phone battery per perf review §"Battery + Thermal Targets". Build will hard-fail if `VideoToolbox`/`MediaCodec` initialization returns an unsupported-codec error; we surface "device not supported" rather than silently fall back.

### 6.2 Frame ID + capture timestamp

Each H.264 access unit carries a PTS in the MPEG-TS PES header. We map PTS → camera-clock-ns using the BLE-broadcast clock anchor (§ multi-camera-sync-spec.md). The frame ID is `(camera_id, monotonic_pts_counter)` — *not* the PTS itself, because PTS wraps every ~26 hours.

### 6.3 Jitter buffer

100 ms target depth. UDP MPEG-TS can deliver out-of-order under Wi-Fi retransmit; we reorder by PTS within the buffer and drop frames whose PTS predates the playhead by more than 200 ms.

### 6.4 Drop policy

**Never drop preview frames at the demux/decode layer.** Backpressure propagates into the ML stage: pose inference is the first to subsample (24 → 10 fps), then YOLO (6 → 3 fps), then post-shot diagnostic. Audio is never dropped. The single mpsc channel between decode and ML uses `try_send`; per-stage drop counters are exposed as OpenTelemetry metrics from Sprint 6 (per perf review §"Instrumentation Plan").

---

## 7. Recording Lifecycle

### 7.1 Hilight tag insertion

`GET /gopro/media/hilight?ts_ms=<ms>` is the documented endpoint; latency 100–400 ms, best-effort. **There is no ack that the tag was written to GPMF until recording stops**, so we maintain a parallel hilight ledger in the local event store (per architect review §"Event Sourcing"):

```
ShotEvent {
  session_id, monotonic_seq, device_clock_ns, server_clock_ns,
  camera_id, hilight_attempted_ts_ns, hilight_http_status,
  audio_xcorr_offset_ns, gpmf_confirmed: Option<bool>
}
```

Post-session, when we pull the file and parse GPMF (§7.3), we set `gpmf_confirmed`. Discrepancies between the local ledger and GPMF are surfaced as report warnings, not silent.

### 7.2 File listing + download

- `GET /gopro/media/list` returns a JSON tree.
- `GET /gopro/media/download/<path>` is chunked transfer; we resume with HTTP Range on transient failures.
- Throughput on 5 GHz: ~80–100 Mbit/s sustained; a 30-min 4K session is ~12 GB and takes 18–24 min to pull. **Download in background while the operator starts the post-session report** — the UI must not gate the report on full file pull.

### 7.3 GPMF metadata extraction

Post-download, we parse GPMF (GoPro Metadata Format) from the MP4 `udta` box for:

- IMU (accel + gyro, 200 Hz)
- GPS (1 Hz, often absent indoors)
- Timecode (audio sample-accurate)
- Hilight markers (the canonical ground truth for shot timestamps)
- Thermal sensor reading (Hero 13 only, ~1 Hz)

Library: `gpmf-rs` (vendored from `gopro/gpmf-parser` C reference, Rust port). All extraction lives in the Rust core; native modules consume parsed structs over UniFFI.

### 7.4 Pause/resume

Stock Hero 13 firmware does **not** support true mid-clip pause — issuing a "pause" stops the clip and starts a new one on resume. We expose `Recording → RecordingPaused` semantically as stop+restart and reconcile via GPMF chapter timestamps post-session. Operator UI clearly labels this as "split clip"; do not lie to the user about pause being mid-clip.

---

## 8. Audio Configuration

Audio is the ground truth for shot detection and the fine-sync anchor for multi-camera (per multi-camera-sync-spec.md §3). Get this right.

### 8.1 Default capture path

- **Sample rate:** 48 kHz
- **Channels:** mono
- **Bit depth:** 16-bit signed PCM
- **Source:** Media Mod 3.5 mm electret cardioid

### 8.2 Encoder latency problem

Stock Hero 13 wraps audio into AAC inside the MP4 with a 20–40 ms encoder lookahead. Sub-shot timing — discriminating two shots 80 ms apart — is degraded by this encoder buffer.

**Recommendation: USB-C UVC raw PCM if achievable** for the federation tier. Hero 13 in webcam mode exposes UAC audio class; we capture 48 kHz mono PCM directly, bypassing AAC. Validation in Sprint 5 — if UAC raw PCM is confirmed, federation tier uses it; otherwise we live with the AAC latency and document it.

### 8.3 Hardware SKUs (consumables)

- **Foam windscreen** — mandatory at >15 km/h wind; Egypt is windy. Spec'd as a sub-$5 SKU shipped with every camera kit.
- **Replacement Media Mod** — 3-month consumable life in dust; spec'd as a recurring SKU.

### 8.4 Multi-shooter audio interference

Two shooters firing within 1.5 s on adjacent stations produce overlapping transients. A simple threshold detector merges them. **V1 mitigation:** per-camera audio + audio-localized shot detector (CRNN over mel features, 30 ms latency per perf review). **V1.5 mitigation:** TDOA mic array — 3-element electret array on a custom Media Mod replacement, time-difference-of-arrival between mics localizes the shot to ±0.5 m. The Rust core's `CameraAudio` trait is designed to accept multi-channel input from V1 to keep V1.5 a drop-in upgrade.

---

## 9. Firmware Version Pinning + Tested Matrix

GoPro pushes Hero 13 firmware roughly every 2 months and **does** break the HTTP API surface. We refuse to operate on untested firmware.

### 9.1 Matrix format

```yaml
- model: HERO13
  firmware: v01.30.00
  open_gopro: 2.0
  app_version: ">=1.0.0,<2.0.0"
  status: certified
  tested_on: 2026-04-12
  tested_by: ci/fixtures/hero13_v01.30.00
  notes: "Baseline for V1 launch."

- model: HERO13
  firmware: v01.40.00
  open_gopro: 2.1
  app_version: ">=1.2.0"
  status: certified
  tested_on: 2026-06-01
  notes: "AP band-switch BLE opcode renumbered; auto-detected via /state."

- model: HERO13
  firmware: v02.00.00
  open_gopro: 2.2
  app_version: "*"
  status: untested
  notes: "No CI fixture run yet — refuses session."

- model: HERO13
  firmware: v01.20.00
  open_gopro: 2.0
  app_version: "*"
  status: known-broken
  notes: "Recording state-machine hang on rapid preset switch; users must update."
```

### 9.2 Startup check

On `start_session`:

1. Read camera firmware via BLE Query service.
2. Look up in compiled-in matrix.
3. If `untested` or absent → modal "We haven't tested AIMVISION on this camera firmware. Update the AIMVISION app, or downgrade the camera firmware to v01.30.00."
4. If `known-broken` → modal "Your camera firmware has a known recording bug. Please update the camera before starting a session."
5. If `certified` → proceed.

### 9.3 CI fixture

Every certified firmware version has a recorded fixture session (BLE/HTTP/UDP captures) in `ci/fixtures/hero13_<version>/`. CI replays it nightly through the full Rust core; any test failure blocks merges to main. Fixtures live in Git LFS (see §12 golden sessions). New firmware versions go through a 1-week soak before status flips from `untested` to `certified`.

### 9.4 Operator override

Power users at Federation tier can bypass the firmware check via a debug-build env var (`AIMVISION_ALLOW_UNTESTED_FIRMWARE=1`). Production builds have no override.

---

## 10. GoPro Labs Firmware Decision

**We commit to supporting Labs firmware as the federation-tier path.**

### 10.1 What Labs unlocks

- `!MSYNC` — precision time sync, BLE-broadcast master clock to slave cameras (~5–15 ms alignment, see multi-cam spec §3).
- Scheduled capture — start/stop on absolute timestamp, not "now".
- QR-code control — print a QR on the operator screen, point each camera at it for one-shot config.
- GPS lock — disable GPS for indoor sessions where the camera otherwise spends 30 s searching.

These are federation-tier-only features. Solo and Club use stock firmware.

### 10.2 The risk

GoPro can revoke Labs at any time. Labs is technically "experimental" and not under any support contract.

### 10.3 Mitigation: dual-supported

The matrix tracks Labs and stock as parallel certified entries:

```yaml
- model: HERO13
  firmware: v01.30.00-labs.2026.04
  open_gopro: 2.0+labs
  status: certified
  tier: federation
  notes: "MSYNC required for federation multi-cam."

- model: HERO13
  firmware: v01.30.00
  open_gopro: 2.0
  status: certified
  tier: solo,club,federation-degraded
  notes: "Federation falls back to audio-xcorr-only sync; ~3× shot-detection variance increase."
```

A federation rig with stock firmware is operational but operates in a "degraded sync" mode (audio cross-correlation only, no MSYNC drift compensation). The report PDF is annotated accordingly.

### 10.4 Decision deadline

This decision is made now (Sprint 3), not Sprint 17 — the multi-cam test rig design (multi-camera-sync-spec.md §8) depends on it.

---

## 11. Outdoor Failure Modes Ranked + Mitigations

Ranked by likelihood per firmware review §"Outdoor Failure Modes". All have engineered mitigations.

### 11.1 Thermal shutdown — Egypt 35–45 °C

Hero 11/12 documented to shut down at 4K60 in ~25 min at 25 °C ambient; Hero 13's Enduro management is improved but still derates. Egypt summer ambient is 35–45 °C in shade, 60 °C+ direct sun on a black plastic camera body.

**Mitigations:**

- **Drop to 2.7K30 for live capture.** 4K is reserved for federation tier with active cooling.
- **White silicone sleeve.** Custom SKU; reflects ~80% of solar load. Mandatory for outdoor sessions.
- **Canopy mount.** Camera lives in the shade of the operator stand canopy, never in direct sun.
- **Cooldown protocol.** 3 min cooldown per 20 min capture at 35 °C+ ambient. The app enforces this — `Recording → RecordingPaused → ThermalCooldown` state on poll exceeding threshold.
- **Thermal-state poll on `Camera` trait.** `fn thermal_state(&self) -> ThermalState { Nominal | Warm | Hot | Critical }`. Polled every 10 s during recording. Hot triggers the 5-fps pose drop (perf review thermal ladder); Critical triggers cooldown.

### 11.2 2.4 GHz Wi-Fi congestion at clubs

Public AP, member phones, range PA systems all live in 2.4 GHz. Hero 13 supports 5 GHz AP.

**Mitigations:**

- **Force 5 GHz** via BLE band-switch on connect. Default for all tiers.
- **Club-AP-conflict detection.** Scan for nearby 5 GHz networks with strong RSSI on the same channel; if collision detected, switch the camera AP to a quieter channel (1, 6, 11 dance for 2.4; 36/40/44/48 for 5 GHz).
- **Phone-tether fallback** for Club operator station. Lightning/USB-C to USB-C dongle, cable-tied to the canopy.

### 11.3 Battery + power

Hero 13 native USB PD accepts 27 W; continuous 4K with screen drains the Enduro battery in ~70 min.

**Mitigations:**

- **USB-C PD power bank, 20 Ah+, 30 W+** spec'd on every camera kit. Anker 737 or equivalent.
- **Powered USB-C hub** at operator station for the operator phone (charging while running ML at 35 °C will sag battery hard).
- **D-Tap option** for federation rigs (shooters' rifles aside, a club-mounted federation rig can run off a single 95 Wh V-mount with D-Tap → USB-C PD distribution).

### 11.4 Audio in multi-shooter environments

See §8.4. **V1: per-camera audio detector. V1.5: TDOA mic array.** Foam windscreen on every camera, every session.

### 11.5 Dust + lens contamination

Media Mod is **not** sealed; 3.5 mm jack and HDMI port are dust gates.

**Mitigations:**

- **Daily lens-and-port wipe protocol.** Microfiber + isopropyl swab. Documented in operator handbook.
- **Spare Media Mod.** 3-month consumable life in range conditions; ships as a kit accessory + recurring SKU.
- **CPL filter** on the lens. Hero 13 supports threaded mods. CPL kills polarized clay-paint glare on orange targets — recovers ~2 stops of effective dynamic range on the target.

---

## 12. Mock Camera + Fixture Grammar

Sprint 17 hardware sync work requires deterministic CI well before real hardware lands.

### 12.1 Fault-injection YAML grammar

```yaml
session:
  duration_s: 90
  cameras:
    - id: cam_a
      model: HERO13
      firmware: v01.30.00
      transport: wifi-5g

events:
  - t: 0.0
    cmd: connect
  - t: 4.5
    cmd: record_start
  - t: 12.3
    cmd: drop_wifi
    duration_s: 4
  - t: 18.0
    cmd: ble_disconnect
  - t: 22.0
    cmd: thermal_warn
    state: Hot
  - t: 30.5
    cmd: shot
    audio_amplitude: 0.92
    transient_ms: 1.5
  - t: 45.0
    cmd: battery_low
    level_pct: 15
  - t: 60.0
    cmd: sd_full
  - t: 75.0
    cmd: record_stop
```

The grammar is parsed by `aimvision-camera-mock` crate, which exposes the same `Camera` trait as the real implementation. CI replays each fault scenario; failures are deterministic and reproducible.

### 12.2 Synthetic multi-camera

Two (or three) mock cameras with configurable clock skew:

```yaml
cameras:
  - id: cam_a
    clock:
      offset_ms: 0
      drift_ppm: 0
      jitter_pdf: gaussian(mean=0, stddev=0.5)
  - id: cam_b
    clock:
      offset_ms: 12.7        # constant offset
      drift_ppm: 8            # 8 ppm linear drift
      jitter_pdf: gaussian(mean=0, stddev=0.8)
```

Shared synthetic shot timeline; the test asserts that the sync code recovers per-shot offsets to within ±1 ms of ground truth. **This is the only way to test sync code before Sprint 17 hardware arrives** (firmware review §"Mock/Fixture Improvements").

### 12.3 Golden sessions in Git LFS

Three real Egypt sessions checked in:

- `golden/egypt_good_lighting.tar` — 25-min session, ~80 shots, baseline.
- `golden/egypt_harsh_sun.tar` — 25-min session, thermal events, mid-session canopy shift.
- `golden/egypt_dust_storm.tar` — 18-min session, lens contamination, BLE flap, Wi-Fi degradation.

Each contains: MPEG-TS preview capture, MP4 + GPMF, ground-truth shot timestamps (manually labelled by Franco's team), and a `manifest.yaml` with expected metrics. CI replays these nightly through the full pipeline and asserts:

- Shot detection F1 ≥ 0.97
- Pose keypoint stability (per-keypoint stddev) within budget
- Report generation time within p50/p95 budget
- No new ERROR-level log lines vs. baseline

Without these, there is no regression detection on ML changes.

---

## 13. Trait Split (per ADR-0003)

The "Camera trait" is split into five focused traits + a capabilities surface. Implementation per vendor implements as many as it can; the app layer queries capabilities at connect time and never assumes.

### 13.1 Traits

```rust
pub trait CameraControl {
    async fn record_start(&self) -> Result<(), CameraError>;
    async fn record_stop(&self) -> Result<RecordingHandle, CameraError>;
    async fn load_preset(&self, preset_id: PresetId) -> Result<(), CameraError>;
    async fn hilight(&self, ts_ns: u64) -> Result<(), CameraError>;
    async fn settings(&self) -> Result<&dyn CameraSettings, CameraError>;
}

pub trait CameraTransport {
    async fn connect(&mut self) -> Result<(), CameraError>;
    async fn disconnect(&mut self) -> Result<(), CameraError>;
    fn link_quality(&self) -> LinkQuality;
    fn negotiate(tier: Tier, caps: &CameraCapabilities) -> TransportChoice;
}

pub trait CameraMedia {
    fn preview_stream(&self) -> Result<PreviewStream, CameraError>;
    async fn list_files(&self) -> Result<Vec<RemoteFile>, CameraError>;
    async fn download_file(&self, path: &str, sink: impl AsyncWrite) -> Result<(), CameraError>;
    async fn extract_gpmf(&self, file: &LocalFile) -> Result<Gpmf, CameraError>;
}

pub trait TimeSource {
    fn now_ns(&self) -> u64;
    fn discipline(&self) -> ClockDiscipline; // Ptp | Ntp | GpsDisciplined | CameraInternal
    fn offset_to(&self, other: &dyn TimeSource) -> Option<i64>;
}

pub trait CameraCapabilities {
    fn live_preview(&self) -> bool;
    fn hilight(&self) -> bool;
    fn external_trigger(&self) -> bool;
    fn dual_band_ap(&self) -> bool;
    fn raw_pcm_audio(&self) -> bool;
    fn thermal_telemetry(&self) -> bool;
    fn imu_gpmf(&self) -> bool;
    fn supports_msync(&self) -> bool;
}
```

### 13.2 Capability-typed events

```rust
pub enum CameraEvent {
    StateChanged(CameraState),
    ThermalWarning(ThermalState),
    BatteryLow(u8),       // 0..=100
    SdFull,
    LinkQualityChanged(LinkQuality),
    ShotDetected { camera_id: CameraId, ts_ns: u64, confidence: f32 },
    Vendor(VendorEvent),  // sealed escape hatch
}

pub struct VendorEvent {
    pub vendor: VendorId,
    pub kind: String,
    pub payload: serde_json::Value,
}
```

The app layer compiles against the strongly-typed events; vendor-specific telemetry (Insta360 stitch quality, custom hardware IMU calibration drift) flows through `Vendor`.

### 13.3 Implementations planned

- `aimvision-camera-gopro` — Hero 13 (Open GoPro 2.0+labs)
- `aimvision-camera-gopro-legacy` — Hero 11 Mini, Hero 12 (supply fallback)
- `aimvision-camera-insta360` — X4 (V1.5; some clubs use them; different stitch semantics)
- `aimvision-camera-phone` — phone-as-camera PWA fallback (Solo tier, ultra-budget)
- `aimvision-camera-aimvision-v3` — custom hardware (V3, placeholder)
- `aimvision-camera-mock` — fixture replay (CI only)

---

## 14. Mounting Hardware Spec

A tripod-mounted camera that drifts mid-session corrupts every shot's geometry. Mount spec is part of the integration spec, not a hardware-team detail.

### 14.1 Tripod

- **Manfrotto 055 class minimum.** Aluminium or carbon, 7+ kg payload, 165 cm max height, ground-spike feet for outdoor concrete pads.
- Spec'd centre column with horizontal arm for overhead/canopy mounts.
- Wind tolerance: stable in 25 km/h gusts; sandbag the spreader for 35+ km/h.

### 14.2 Mount torque

- **GoPro thumbscrew torqued to 0.6 N·m** with a small torque key included in the operator kit. Hand-tight is not enough — vibration walks the mount loose over a 2 hr session.
- 1/4"-20 to GoPro adapter spec'd for the tripod head.

### 14.3 Optical accessories

- **CPL filter** (52 mm threaded mod for Hero 13) for orange-clay glare.
- **Foam windscreen** on the Media Mod (mandatory).
- **Canopy shade** — the camera lives under the operator stand canopy in direct sun.

### 14.4 V2+ gun-mounted SKU

For any V2+ shooter-mounted camera (helmet cam, gun rail cam):

- **Anti-vibration isolators** rated for 30–50 G recoil impulse. Sorbothane mount or Picatinny rail with rubber dampener.
- **Auto-recalibrate trigger** when GPMF IMU delta exceeds threshold (`||gyro_var - baseline|| > 3σ`). This forces a re-prompt for the ChArUco calibration step before the next string.

---

## 15. External Trigger (V1.5+)

Hero 13 has **no GPIO**. The only "trigger" path is the BLE shutter command — measured 80–150 ms latency, jitter ±25 ms. **Not viable for competition-timer sub-frame triggering.**

### 15.1 Alternatives investigated

- **BLE shutter** — current state of the art; ~80–150 ms latency. Acceptable for "start the recording" but not for per-shot trigger.
- **GoPro Wired Remote** — older mods used a custom 2.5 mm jack pinout; Hero 13 routes this through USB-C HID. **Spec sheet partially documented; requires reverse-engineering with a Saleae Pro 16.**
- **USB-C HID** — most promising for V1.5/V2. Standard HID class device (e.g., a microcontroller on a Pi Pico) that the camera enumerates as a remote. Latency target: <20 ms. **Investigation gated to before V2 hardware roadmap solidifies — Sprint 14.**

### 15.2 What we ship in V1

BLE shutter + audio cross-correlation post-detection. The audio anchor is what gives us sub-ms shot timing; the trigger only needs to start the recording within a few hundred ms.

### 15.3 V1.5 plan

Build a USB-C HID adapter prototype (Pi Pico + Open GoPro USB HID protocol). Validate <20 ms latency. Spec as a federation-tier accessory for competition timer integration.

---

## 16. Vendor Lock-in Escape Paths

Trait-level support for non-GoPro cameras is mandatory from V1 even though we ship GoPro-only.

### 16.1 Roadmap

| Vendor / form factor | Tier | Status |
|---|---|---|
| Hero 13 (stock + Labs) | All tiers | V1 P0 |
| Hero 11 Mini | Solo budget | V1.5 (supply fallback when Hero 13 unobtainable) |
| Hero 12 | Solo / Club | V1 P1 (matrix entry, untested but architecturally supported) |
| Insta360 X4 | Club (some clubs already use them) | V1.5 — different stitch semantics, requires `CameraMedia` impl that flattens to flat sensor virtual frames |
| Phone-as-camera (PWA) | Solo ultra-budget | V2 — PWA grabs phone camera + local audio, uploads MP4 + ground-truth ts; analytics run server-side only |
| Custom AIMVISION hardware V3 | Federation premium | V3 — IMU-on-camera, GPS-disciplined timecode, hardware genlock, USB-C HID trigger |

### 16.2 What this buys us

- **Supply resilience.** GoPro is one company. If they pivot, brick our firmware version, or revoke Labs, we have a path.
- **Tier expansion.** Phone-as-camera unlocks a $0-hardware Solo tier.
- **Competitive moat in V3.** Custom hardware with sub-ms hardware-level sync is the federation differentiator nobody else has.

### 16.3 What we are NOT doing

- DJI cameras — locked SDK, no preview tap, no.
- Sony alpha — interesting, but professional-cinema price points don't fit any tier.
- IP/PoE security cameras — wrong form factor for shooters.

---

## Appendix A: Acronyms

- **AAC** — Advanced Audio Coding
- **AP** — Access Point (camera-as-WiFi-AP mode)
- **BLE** — Bluetooth Low Energy
- **CBPeripheral** — CoreBluetooth's peripheral abstraction (iOS)
- **CPL** — Circular Polarizing (filter)
- **CRNN** — Convolutional Recurrent Neural Network
- **GATT** — Generic Attribute Profile (BLE)
- **GPMF** — GoPro Metadata Format
- **HID** — Human Interface Device
- **MPEG-TS** — MPEG Transport Stream
- **MSYNC** — Open GoPro Labs precision time-sync command
- **PD** — USB Power Delivery
- **PSM** — Power Save Mode (Wi-Fi)
- **PTS** — Presentation Time Stamp
- **TDOA** — Time Difference Of Arrival
- **UAC** — USB Audio Class
- **UVC** — USB Video Class

## Appendix B: References

- Open GoPro 2.0 specification — `https://gopro.github.io/OpenGoPro/`
- Open GoPro Labs documentation — `https://gopro.github.io/labs/`
- `gpmf-parser` reference C implementation — `https://github.com/gopro/gpmf-parser`
- `docs/reviews/05-embedded-firmware-engineer.md`
- `docs/reviews/10-performance-benchmarker.md`
- `docs/reviews/03-software-architect.md`
- `docs/adr/ADR-0003-camera-trait-split.md` (TODO: write)
