# aimvision-camera-core

Rust workspace implementing the camera-core traits, mock implementation, and
connection state machine for AIMVISION. This is the canonical control-plane
surface that V1 ships to iOS (via UniFFI), Android (via UniFFI), and the
Federation on-prem appliance (native).

See:

- [`docs/adr/0003-rust-camera-core-split.md`](../docs/adr/0003-rust-camera-core-split.md) — the ADR that justifies the split-trait surface and the FFI strategy.
- [`docs/camera-integration-spec.md`](../docs/camera-integration-spec.md) — protocol contract, command queue, state machine, fixtures.
- [`docs/multi-camera-sync-spec.md`](../docs/multi-camera-sync-spec.md) — `!MSYNC` + audio xcorr sync architecture and the synthetic 2-camera test rig.

## Crates

| Crate                     | Purpose                                                                                                                                                                                                                                      |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `aimvision-camera-traits` | Pure interface crate. No implementations. The trait split per ADR-0003: `CameraControl`, `CameraTransport`, `CameraMedia`, `TimeSource`.                                                                                                     |
| `aimvision-camera-mock`   | Fixture-driven mock implementation. Parses YAML fault scripts and replays them deterministically. Powers CI before real hardware lands in Sprint 17.                                                                                         |
| `aimvision-camera-phone`  | Dev-mode phone backend ([ADR-0009](../docs/adr/0009-phone-capture-dev-backend.md)). Accepts frames pushed in from a `react-native-vision-camera` worklet shim. Slice 3a lands the safe-Rust push API; slice 3c adds the `extern "C"` bridge. |
| `aimvision-camera-state`  | Connection state machine + single-in-flight command queue with 2 s watchdog and jittered exponential backoff.                                                                                                                                |

## Quickstart

```bash
cd aimvision-camera-core
cargo test --workspace
```

This runs the full test suite, including:

- Exhaustive `ConnectionState` transition matrix.
- `CommandQueue` serial-execution + watchdog tests.
- Mock playback against `fixtures/sample_session.yaml`.
- Fault-injection (`drop_wifi`) reconnect path.
- Two-camera audio cross-correlation alignment recovery on synthesized muzzle blast.

## Style

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
```

`-D warnings` is enforced by `.cargo/config.toml` for local builds and by the
CI workflow at `.github/workflows/camera-core-ci.yml`.

## MSRV

Pinned to **Rust 1.83** via `rust-toolchain.toml`. Bumping the MSRV is a
deliberate release-management event because UniFFI bindings track
`uniffi-rs` which itself pins toolchain compatibility per minor version
(see ADR-0003 §"FFI strategy").

## Status

V1 P0. Federation 2-camera scope is **architecture-only** in V1 — the schema,
traits, and synthetic 2-camera rig are in place; real-hardware multi-cam
validation lands in V1.5 per `docs/multi-camera-sync-spec.md` §9.
