# ADR-0003: Rust Camera-Core with Split Traits, UniFFI Control Plane, `extern "C"` Media Plane

**Status:** Accepted (with a re-evaluation gate at end of Phase 2) · **Date:** 2026-05-06 · **Owner:** Software Architect (with Embedded Firmware Engineer concurrence)

## Context

The V1 plan calls for a Rust core (`aimvision-camera-core`) wrapped via UniFFI for use from Swift and Kotlin. The [Software Architect review §Top 3 #1](../reviews/03-software-architect.md) flagged this as the most questionable decision in V1: writing the GoPro Hero 13 protocol stack (BLE pairing, HTTP/1.1 control, MP4 file pulls, UDP/RTP preview) in Rust and exporting it through UniFFI introduces three async runtimes (Tokio, GCD, Kotlin coroutines), two FFI surfaces, and a hiring pool of maybe 200 engineers globally who can do all three competently — for what may be a few thousand lines of unglamorous protocol code that could ship faster as TypeScript with `react-native-ble-plx` plus thin Swift/Kotlin USB modules.

That review's bottom line: the Rust core only pays off if (a) the protocol logic exceeds ~5k lines and changes often, (b) the same core runs on a desktop/edge/Linux federation appliance, or (c) DSP/CV code lands in the same crate. The [Embedded review](../reviews/05-embedded-firmware-engineer.md) confirms (a): when you account for BLE bond clearing, Wi-Fi AP backgrounding recovery, the HTTP API serialization watchdog, multi-camera time sync (`!MSYNC` + audio cross-correlation), firmware version pinning and feature negotiation, ChArUco calibration, and a fault-injection mock harness, you are at 5–8k lines of stateful, tricky code. (b) is the federation on-prem appliance (ADR-0005) which runs the same core to drive locally-attached cameras. (c) is the V2 plan for custom AIMVISION hardware and a microphone array on the camera mount ([AI Engineer review §Smarter-feature differentiators](../reviews/01-ai-engineer.md)).

So the Rust core is justified — _if and only if V2 hardware or the on-prem appliance materializes._ This ADR enshrines that "if" as a Phase 2 re-evaluation gate.

The [Mobile review §2](../reviews/04-mobile-app-builder.md) provides the second-half guidance: UniFFI is the right call for the control plane (it handles structs, enums, async, traits, and callbacks well; it is used in production by Firefox sync, Matrix Rust SDK, Bitwarden, Signal-rs ports, Glean, Nimbus) but is **not** the right call for the frame-data hot path (zero-copy buffer sharing and callback-heavy hot loops are weak spots). The pin-the-version concern is real: the proc-macro UDL changed twice in 2024–2025 and broke iOS+Android bindings simultaneously.

The [Embedded review §Trait Design](../reviews/05-embedded-firmware-engineer.md) provides the trait split: a single fat `Camera` trait does not survive contact with Insta360 X4 (a 360 stitch, not a flat sensor) or future custom hardware (different clock disciplines: PTP, NTP, GPS-disciplined). The right shape is to split by concern.

## Decision

**A single Rust workspace `aimvision-camera-core` with a deliberately split trait surface, UniFFI for the control plane only, hand-written `extern "C"` for the media plane, and an explicit re-evaluation gate at end of Phase 2.**

### Trait split

```rust
pub trait CameraControl: Send + Sync {
    async fn pair(&self, peer: PeerId) -> Result<()>;
    async fn unpair(&self) -> Result<()>;             // includes BLE bond clearing
    async fn set_mode(&self, mode: CaptureMode) -> Result<()>;
    async fn start_recording(&self) -> Result<RecordingHandle>;
    async fn stop_recording(&self) -> Result<()>;
    async fn hilight(&self, ts: Instant) -> Result<HilightAck>;
    fn capabilities(&self) -> &CameraCapabilities;
    fn time_source(&self) -> &dyn TimeSource;
    fn events(&self) -> EventStream;                  // sealed enum, not stringly-typed
}

pub trait CameraTransport: Send + Sync {
    async fn connect_ble(&self) -> Result<BleSession>;
    async fn connect_wifi_ap(&self, band: WifiBand) -> Result<WifiSession>;
    async fn connect_uvc(&self) -> Result<UvcSession>;       // USB-C tether (federation tier)
    fn diagnostics(&self) -> TransportDiagnostics;            // RSSI, link state, drop counters
}

pub trait CameraMedia: Send {
    fn frame_handles(&self) -> FrameHandleStream;             // opaque IOSurface/AHardwareBuffer ids
    fn audio_pcm(&self) -> AudioPcmStream;                    // raw PCM, not AAC-decoded
}

pub trait TimeSource: Send + Sync {
    fn now(&self) -> Instant;
    fn discipline(&self) -> ClockDiscipline;                  // NTP / PTP / GPS / cameraLabsMSYNC
    fn offset_to(&self, other: &dyn TimeSource) -> Duration;  // for multi-cam sync
}

pub struct CameraCapabilities {
    pub live_preview: bool,
    pub hilight: bool,
    pub external_trigger: bool,
    pub usb_uvc: bool,
    pub multicam_sync: Option<MultiCamSyncProtocol>,
    pub audio_channels: u8,
    pub audio_sample_rate_hz: u32,
    pub audio_bit_depth: u8,
    pub max_resolution: Resolution,
    pub thermal_telemetry: bool,
    // ...
}

pub enum CameraEvent {
    ThermalWarning(ThermalState),
    BatteryLow(u8),                  // percent
    SdFull,
    LinkDegraded(LinkQuality),
    Vendor(VendorEvent),             // forward-compat escape hatch
}
```

### FFI strategy

- **Control plane** (`CameraControl`, `CameraTransport`, `CameraCapabilities`, `TimeSource`, events): exported via **UniFFI**. UniFFI generates Swift and Kotlin bindings from `.udl` definitions; we pin `uniffi-rs` to a specific minor version per release and re-vendor on update. Battle-tested precedents: `matrix-rust-sdk`, `bitwarden-sdk`, `glean-core`, `nimbus-fml`. UniFFI handles async, structs, enums, traits, and callbacks; we explicitly do not use it for buffers.
- **Media plane** (`CameraMedia`): exported via a hand-written **`#[no_mangle] extern "C"` C ABI**. Frame handles are `uint32` `IOSurface` IDs on iOS and `AHardwareBuffer*` on Android; Swift wraps them as `CVPixelBuffer` and feeds Skia/Metal; Kotlin wraps them as `HardwareBuffer` and feeds Skia/GL. **The Rust core never touches pixels for live preview** — it only manages the handle lifecycle and the audio PCM stream. ML inference reads the same buffer via `MLMultiArray` (Core ML) or `TensorImage` (NNAPI) zero-copy adaptors.

### Implementations

V1 ships `Hero13Camera` (Open GoPro: BLE GATT services for command/setting/query, Wi-Fi AP control, USB-C UVC) and `MockCamera` (consumes a YAML fault-injection script — `t=12.3s drop_wifi for 4s`, `t=22s thermal_warn`, etc., per [Embedded review §Mock improvements](../reviews/05-embedded-firmware-engineer.md)). V2-planned: `Insta360X4Camera` and `AimvisionHardwareCamera`. Each implementation declares its `CameraCapabilities`; callers ask "does this camera support hilight?" instead of calling and getting `Err(Unsupported)`.

### Re-evaluation gate

**At the end of Phase 2 (post-Sprint 18), the architecture committee reviews the Rust-core decision against three criteria:** has V2 hardware materialized; is the on-prem appliance shipping with locally-attached cameras; has the camera protocol code base exceeded 5k lines with active churn? If two of three are false, the protocol layer is rewritten in TypeScript+Swift+Kotlin and the Rust crate is retired or scoped to ML-on-device only.

## Consequences

**Easier:**

- One protocol implementation across iOS, Android, and the federation Linux appliance.
- Stable trait surface for callers: capabilities are queried, not discovered through errors.
- Forward compatibility for new camera vendors and time disciplines without breaking existing call sites.
- Multi-camera sync (Hero 13 `!MSYNC` + audio cross-correlation per [Embedded §Multi-Camera Sync](../reviews/05-embedded-firmware-engineer.md)) lives in `TimeSource` implementations, not as bolt-ons.
- Fault-injection mock makes Sprint 17 (multi-cam validation) a one-week sprint instead of an eight-week sprint.

**Harder:**

- Three async runtimes (Tokio in Rust, GCD in iOS, Kotlin coroutines in Android) require disciplined cancellation propagation. We mitigate with structured concurrency on the Rust side and a single `CancellationToken` plumbed through every async call.
- UniFFI version pinning becomes a release-management concern. Every UniFFI bump is treated as a breaking change to the mobile app and gated on a full QA pass.
- The hiring pool for "Rust + iOS Swift + Android Kotlin + async" engineers is small. We mitigate by partitioning roles (Rust core is one engineer's specialty; mobile FFI integration is another's) and by leaning on the precedent-rich UniFFI pattern.
- Maintaining a hand-written C ABI alongside UniFFI is two FFI surfaces. We mitigate by keeping the C ABI surface tiny — handle pass-through and audio PCM pump only.

**Reversibility:** Low after Sprint 6. We pay this cost upfront and the re-evaluation gate at Phase 2 is the formal off-ramp.

## Alternatives Considered

1. **TypeScript protocol layer with `react-native-ble-plx` + `fetch` + thin Swift/Kotlin USB modules.** Ships faster, hires from a larger pool, no FFI tax. Rejected because (a) the federation on-prem appliance needs the same protocol layer and there is no React Native there, (b) custom AIMVISION hardware in V2 needs the protocol logic on Linux, and (c) BLE bond management plus Wi-Fi AP recovery on iOS background is genuinely intricate and benefits from a single canonical implementation.
2. **KMM (Kotlin Multiplatform Mobile) for the protocol layer.** Same interop tax as Rust+UniFFI, weaker async story (Kotlin/Native coroutines on iOS are a known pain point), no Linux desktop story. Rejected.
3. **Pure-Rust including UniFFI for the media plane.** Rejected because UniFFI does not do zero-copy buffer sharing well and the frame path cannot afford a copy. The hand-written C ABI for the media plane is the right scalpel.
4. **Single fat `Camera` trait.** Rejected per [Embedded §Trait Design Changes](../reviews/05-embedded-firmware-engineer.md). Insta360 X4 is a 360 stitch, not a flat sensor, and a fat trait forces it to lie about its semantics or return `Unsupported` everywhere.
5. **Float `uniffi-rs` to latest.** Rejected. The proc-macro UDL changed twice in 2024–2025 and broke iOS+Android bindings simultaneously. Pinning is mandatory.

## References

- [Software Architect review §Top 3 #1](../reviews/03-software-architect.md) — the original challenge to the Rust-core decision and the conditions under which it pays off.
- [Mobile App Builder review §2](../reviews/04-mobile-app-builder.md) — UniFFI for control plane only, hand-written C ABI for media, version pinning.
- [Embedded Firmware Engineer review](../reviews/05-embedded-firmware-engineer.md) — trait split (`CameraControl`/`CameraTransport`/`CameraMedia`/`TimeSource`/`CameraCapabilities`), capability-typed events, mock fault-injection grammar, firmware pinning matrix.
- UniFFI: <https://mozilla.github.io/uniffi-rs/>
- `matrix-rust-sdk`: <https://github.com/matrix-org/matrix-rust-sdk>
- `bitwarden-sdk`: <https://github.com/bitwarden/sdk>
- Open GoPro spec: <https://gopro.github.io/OpenGoPro/>
