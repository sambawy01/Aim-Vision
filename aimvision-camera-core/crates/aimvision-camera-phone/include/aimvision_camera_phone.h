/*
 * aimvision_camera_phone.h
 *
 * C ABI for the AIMVISION dev-mode phone camera backend
 * (ADR-0009 §17.3c, ADR-0003 media-plane FFI).
 *
 * Hand-written to match `src/ffi.rs`. If you edit one, edit both — there
 * is no codegen step.
 *
 * # ABI stability
 *
 * The shape of this header (struct layout, function signatures, enum
 * discriminants) is the wire format between the Rust crate and the
 * platform shim layer in
 * `aimvision-mobile/plugins/phone-frame-sink/{ios,android}`. Both ship
 * from the same git revision, so we do not version this header — bump
 * versions only if the shim layer ever ships out-of-tree.
 *
 * # Calling thread
 *
 * Functions on this surface are thread-safe (the Rust side uses interior
 * mutability behind an `Arc<Mutex<...>>`). They are called from the
 * Vision Camera worklet thread on every frame; do not introduce locks
 * higher in the stack that would defeat that.
 *
 * # Caller responsibilities
 *
 * See the "Caller contract" section in `src/ffi.rs`. The short version:
 * `_new` returns a handle; pass it to every subsequent call; release
 * exactly once with `_free` (or leak intentionally for the lifetime of
 * the process).
 */

#ifndef AIMVISION_CAMERA_PHONE_H
#define AIMVISION_CAMERA_PHONE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Frame format. Integer values are stable wire-format — never reorder,
 * only ever append.
 */
typedef enum {
    AIMVISION_FRAME_FORMAT_NV12 = 0,
    AIMVISION_FRAME_FORMAT_I420 = 1,
    AIMVISION_FRAME_FORMAT_RGBA8 = 2,
} AimvisionFrameFormat;

/* Opaque handle — defined in the Rust crate. */
typedef struct AimvisionPhoneCamera AimvisionPhoneCamera;

/*
 * Construct a phone-camera backend.
 *
 * `id`               : NUL-terminated UTF-8 identifier (e.g. "phone-0").
 *                      Lifetime must outlast the call (Rust copies the string).
 * `frame_capacity`   : Per-camera frame ring-buffer size (>= 1).
 * `audio_capacity`   : Per-camera audio ring-buffer size (>= 1).
 *
 * Returns NULL on:
 *   - NULL id
 *   - non-UTF-8 id
 *   - zero capacity for either ring
 */
AimvisionPhoneCamera *aimvision_phone_camera_new(const char *id,
                                                 size_t frame_capacity,
                                                 size_t audio_capacity);

/*
 * Release a phone camera. NULL is permitted (no-op) so the caller can
 * release unconditionally after a possibly-failed _new.
 */
void aimvision_phone_camera_free(AimvisionPhoneCamera *handle);

/*
 * Push a frame *handle* — NOT pixel bytes.
 *
 * `handle_id` is the platform-opaque identifier (IOSurface ID on iOS,
 * low 64 bits of an AHardwareBuffer pointer on Android). The Rust core
 * never dereferences this; it ferries the value to ML consumers who own
 * the platform-side decoding step.
 *
 * Returns true if a queued frame was evicted to make room. Returns
 * false on NULL handle (push silently dropped — by design, the worklet
 * thread cannot afford a panic per frame).
 */
bool aimvision_phone_camera_push_frame(AimvisionPhoneCamera *handle,
                                       AimvisionFrameFormat format,
                                       uint64_t handle_id,
                                       uint32_t width,
                                       uint32_t height,
                                       uint64_t pts_ns,
                                       uint64_t monotonic_seq);

/*
 * Push a chunk of PCM audio. Samples are copied into the queue before
 * the call returns — the caller's buffer may be freed immediately.
 *
 * n_samples = samples_per_channel * channels (interleaved PCM).
 *
 * Empty chunks (n_samples == 0) are permitted; samples_ptr may then be
 * NULL.
 *
 * Returns true if a queued chunk was evicted. Returns false on:
 *   - NULL handle
 *   - NULL samples_ptr with n_samples > 0
 *   - otherwise; the chunk was queued and nothing was evicted
 */
bool aimvision_phone_camera_push_audio_chunk(AimvisionPhoneCamera *handle,
                                             const int16_t *samples_ptr,
                                             size_t n_samples,
                                             uint32_t sample_rate_hz,
                                             uint8_t channels,
                                             uint64_t start_ts_ns);

/*
 * Cumulative frames dropped on overflow since _new. Returns 0 on NULL handle.
 */
uint64_t aimvision_phone_camera_dropped_frames(const AimvisionPhoneCamera *handle);

/*
 * Cumulative audio chunks dropped on overflow since _new. Returns 0 on NULL handle.
 */
uint64_t aimvision_phone_camera_dropped_audio(const AimvisionPhoneCamera *handle);

#ifdef __cplusplus
}
#endif

#endif /* AIMVISION_CAMERA_PHONE_H */
