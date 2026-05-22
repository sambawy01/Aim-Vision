/**
 * Phone-capture recording state machine — Sprint 4 dev-mode camera backend
 * slice 1 ([ADR-0009](../../../docs/adr/0009-phone-capture-dev-backend.md)).
 *
 * Pure TS. No imports from `react-native-vision-camera` so the reducer is
 * unit-testable without a device or any native module mocks. The
 * `CapturePhoneScreen` consumes this via `useReducer` and translates UI
 * actions / Vision Camera callbacks into events.
 *
 * Lifecycle:
 *
 *   unknown
 *     ├── request-permission ───────────┐
 *     ▼                                 │
 *   permission-pending ─── grant ──▶ ready ─── start ──▶ recording
 *     │                                 ▲                  │
 *     └── deny ──▶ permission-denied    │                  │
 *                                       │                  ▼
 *                                       │              stopping
 *                                       │                  │
 *                                       │             finalize(uri)
 *                                       │                  │
 *                                       │                  ▼
 *                                       └── reset ──── idle-with-recording
 *
 *   error is a terminal-ish state reachable from `permission-pending`,
 *   `recording`, or `stopping`; `reset` rehydrates to `ready` if
 *   permissions are still held, otherwise to `unknown`.
 *
 * Why a reducer, not zustand: this state is intrinsically scoped to a
 * single screen-lifetime, not app-global. A zustand store would leak
 * across screen mounts and force teardown plumbing for no upside.
 */

export type RecordingStatus =
  | 'unknown'
  | 'permission-pending'
  | 'permission-denied'
  | 'ready'
  | 'recording'
  | 'stopping'
  | 'idle-with-recording'
  | 'uploading'
  | 'uploaded'
  | 'upload-failed'
  | 'error';

export interface RecordingState {
  status: RecordingStatus;
  /** Most recent finalized recording's local file URI, or null if none. */
  lastRecordingUri: string | null;
  /** Wall-clock ms when the *current* recording started; null when not recording. */
  recordingStartedAt: number | null;
  /** Human-readable error message; only meaningful in status="error". */
  errorMessage: string | null;
  /** True iff the user has previously granted permissions in this session.
   * Distinct from `status === 'ready'` because `recording`/`stopping`/`idle-with-recording`
   * all imply the permission is still held. */
  permissionGranted: boolean;
  /** Backend recording id once the finalized clip has been uploaded; null otherwise. */
  uploadedRecordingId: string | null;
  /** Human-readable upload error; only meaningful in status="upload-failed". */
  uploadError: string | null;
}

export type RecordingEvent =
  | { kind: 'request-permission' }
  | { kind: 'permission-granted' }
  | { kind: 'permission-denied'; reason?: string }
  | { kind: 'start-recording' }
  | { kind: 'recording-started'; at: number }
  | { kind: 'stop-recording' }
  | { kind: 'recording-finalized'; uri: string }
  | { kind: 'upload-started' }
  | { kind: 'upload-succeeded'; recordingId: string }
  | { kind: 'upload-failed'; message: string }
  | { kind: 'error'; message: string }
  | { kind: 'reset' };

export const INITIAL_RECORDING_STATE: RecordingState = {
  status: 'unknown',
  lastRecordingUri: null,
  recordingStartedAt: null,
  errorMessage: null,
  permissionGranted: false,
  uploadedRecordingId: null,
  uploadError: null,
};

/** Pure transition function. Illegal transitions return the state unchanged
 * so the screen never crashes on a stale callback; callers can detect a
 * no-op by reference equality (`next === prev`). */
export function recordingReducer(state: RecordingState, event: RecordingEvent): RecordingState {
  switch (event.kind) {
    case 'request-permission': {
      // Only allowed from unknown or permission-denied. From any other
      // state we already have a decision and should not retrigger the
      // OS prompt (which the OS will silently swallow anyway after the
      // first denial on iOS).
      if (state.status !== 'unknown' && state.status !== 'permission-denied') {
        return state;
      }
      return { ...state, status: 'permission-pending', errorMessage: null };
    }

    case 'permission-granted': {
      if (state.status !== 'permission-pending') return state;
      return { ...state, status: 'ready', permissionGranted: true };
    }

    case 'permission-denied': {
      if (state.status !== 'permission-pending') return state;
      return {
        ...state,
        status: 'permission-denied',
        permissionGranted: false,
        errorMessage: event.reason ?? null,
      };
    }

    case 'start-recording': {
      // Allowed from `ready`, `idle-with-recording`, and after an upload
      // settled (`uploaded` / `upload-failed`) so the user can shoot a
      // follow-up take. Not allowed mid-`uploading`. The native
      // `recordingStartedAt` is filled in by `recording-started` once
      // Vision Camera confirms.
      if (
        state.status !== 'ready' &&
        state.status !== 'idle-with-recording' &&
        state.status !== 'uploaded' &&
        state.status !== 'upload-failed'
      ) {
        return state;
      }
      return {
        ...state,
        status: 'recording',
        errorMessage: null,
        uploadError: null,
        uploadedRecordingId: null,
      };
    }

    case 'recording-started': {
      if (state.status !== 'recording') return state;
      return { ...state, recordingStartedAt: event.at };
    }

    case 'stop-recording': {
      if (state.status !== 'recording') return state;
      return { ...state, status: 'stopping' };
    }

    case 'recording-finalized': {
      if (state.status !== 'stopping') return state;
      return {
        ...state,
        status: 'idle-with-recording',
        lastRecordingUri: event.uri,
        recordingStartedAt: null,
      };
    }

    case 'upload-started': {
      // Kick off an upload of the finalized clip. Allowed from
      // `idle-with-recording` (fresh clip) or `upload-failed` (retry).
      if (state.status !== 'idle-with-recording' && state.status !== 'upload-failed') {
        return state;
      }
      return { ...state, status: 'uploading', uploadError: null };
    }

    case 'upload-succeeded': {
      if (state.status !== 'uploading') return state;
      return {
        ...state,
        status: 'uploaded',
        uploadedRecordingId: event.recordingId,
        uploadError: null,
      };
    }

    case 'upload-failed': {
      if (state.status !== 'uploading') return state;
      return { ...state, status: 'upload-failed', uploadError: event.message };
    }

    case 'error': {
      // Reachable from permission-pending, recording, or stopping. From
      // other statuses we ignore — a spurious error after success would
      // otherwise wipe the lastRecordingUri.
      if (
        state.status !== 'permission-pending' &&
        state.status !== 'recording' &&
        state.status !== 'stopping'
      ) {
        return state;
      }
      return {
        ...state,
        status: 'error',
        errorMessage: event.message,
        recordingStartedAt: null,
      };
    }

    case 'reset': {
      // If we already have permission, drop back to `ready` so the user
      // can simply tap record again. Otherwise re-prompt from `unknown`.
      return {
        ...state,
        status: state.permissionGranted ? 'ready' : 'unknown',
        errorMessage: null,
        recordingStartedAt: null,
        uploadError: null,
        uploadedRecordingId: null,
      };
    }
  }
}

/** Convenience: does this state allow starting a new recording right now? */
export function canStartRecording(state: RecordingState): boolean {
  return (
    state.status === 'ready' ||
    state.status === 'idle-with-recording' ||
    state.status === 'uploaded' ||
    state.status === 'upload-failed'
  );
}

/** Convenience: is there a finalized clip ready to upload (or retry)? */
export function canUpload(state: RecordingState): boolean {
  return (
    (state.status === 'idle-with-recording' || state.status === 'upload-failed') &&
    state.lastRecordingUri !== null
  );
}

/** Convenience: is a recording actively underway? */
export function isActivelyRecording(state: RecordingState): boolean {
  return state.status === 'recording';
}
