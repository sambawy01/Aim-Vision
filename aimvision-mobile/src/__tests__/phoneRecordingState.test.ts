/**
 * Phone-capture state machine unit tests — ADR-0009 slice 1.
 *
 * Pure-TS coverage of the reducer in `src/capture/phoneRecordingState.ts`.
 * No device, no Vision Camera, no jest mocks needed.
 */
import {
  canStartRecording,
  INITIAL_RECORDING_STATE,
  isActivelyRecording,
  recordingReducer,
  type RecordingState,
} from '../capture/phoneRecordingState';

describe('phone recording state machine', () => {
  describe('permission flow', () => {
    it('moves unknown → permission-pending on request', () => {
      const next = recordingReducer(INITIAL_RECORDING_STATE, {
        kind: 'request-permission',
      });
      expect(next.status).toBe('permission-pending');
    });

    it('moves permission-pending → ready on grant', () => {
      const requested = recordingReducer(INITIAL_RECORDING_STATE, {
        kind: 'request-permission',
      });
      const granted = recordingReducer(requested, { kind: 'permission-granted' });
      expect(granted.status).toBe('ready');
      expect(granted.permissionGranted).toBe(true);
    });

    it('moves permission-pending → permission-denied with reason captured', () => {
      const requested = recordingReducer(INITIAL_RECORDING_STATE, {
        kind: 'request-permission',
      });
      const denied = recordingReducer(requested, {
        kind: 'permission-denied',
        reason: 'user declined',
      });
      expect(denied.status).toBe('permission-denied');
      expect(denied.permissionGranted).toBe(false);
      expect(denied.errorMessage).toBe('user declined');
    });

    it('allows re-request from permission-denied (re-prompt path)', () => {
      const denied: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'permission-denied',
      };
      const next = recordingReducer(denied, { kind: 'request-permission' });
      expect(next.status).toBe('permission-pending');
      expect(next.errorMessage).toBeNull();
    });

    it('ignores request-permission from ready (already decided)', () => {
      const ready: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'ready',
        permissionGranted: true,
      };
      const next = recordingReducer(ready, { kind: 'request-permission' });
      // Same reference -> no-op, so the screen knows nothing happened.
      expect(next).toBe(ready);
    });

    it('ignores permission-granted from a non-pending state', () => {
      const ready: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'ready',
        permissionGranted: true,
      };
      const next = recordingReducer(ready, { kind: 'permission-granted' });
      expect(next).toBe(ready);
    });
  });

  describe('recording flow', () => {
    function readyState(): RecordingState {
      return {
        ...INITIAL_RECORDING_STATE,
        status: 'ready',
        permissionGranted: true,
      };
    }

    it('start-recording transitions ready → recording', () => {
      const next = recordingReducer(readyState(), { kind: 'start-recording' });
      expect(next.status).toBe('recording');
      expect(next.errorMessage).toBeNull();
    });

    it('recording-started fills in recordingStartedAt', () => {
      let s = recordingReducer(readyState(), { kind: 'start-recording' });
      s = recordingReducer(s, { kind: 'recording-started', at: 1234567890 });
      expect(s.recordingStartedAt).toBe(1234567890);
      expect(s.status).toBe('recording');
    });

    it('stop-recording transitions recording → stopping', () => {
      let s = recordingReducer(readyState(), { kind: 'start-recording' });
      s = recordingReducer(s, { kind: 'recording-started', at: 100 });
      s = recordingReducer(s, { kind: 'stop-recording' });
      expect(s.status).toBe('stopping');
    });

    it('recording-finalized transitions stopping → idle-with-recording and stores the URI', () => {
      let s = recordingReducer(readyState(), { kind: 'start-recording' });
      s = recordingReducer(s, { kind: 'recording-started', at: 100 });
      s = recordingReducer(s, { kind: 'stop-recording' });
      s = recordingReducer(s, {
        kind: 'recording-finalized',
        uri: 'file:///tmp/aimvision-1.mp4',
      });
      expect(s.status).toBe('idle-with-recording');
      expect(s.lastRecordingUri).toBe('file:///tmp/aimvision-1.mp4');
      expect(s.recordingStartedAt).toBeNull();
    });

    it('start-recording from idle-with-recording re-arms for a follow-up take', () => {
      const idle: RecordingState = {
        status: 'idle-with-recording',
        lastRecordingUri: 'file:///tmp/aimvision-1.mp4',
        recordingStartedAt: null,
        errorMessage: null,
        permissionGranted: true,
      };
      const next = recordingReducer(idle, { kind: 'start-recording' });
      expect(next.status).toBe('recording');
      // Previous recording's URI is preserved until the next finalize.
      expect(next.lastRecordingUri).toBe('file:///tmp/aimvision-1.mp4');
    });

    it('rejects start-recording from unknown / permission-denied', () => {
      for (const status of ['unknown', 'permission-denied', 'recording'] as const) {
        const s: RecordingState = { ...INITIAL_RECORDING_STATE, status };
        const next = recordingReducer(s, { kind: 'start-recording' });
        expect(next).toBe(s);
      }
    });

    it('ignores stop-recording when not currently recording', () => {
      const ready = readyState();
      const next = recordingReducer(ready, { kind: 'stop-recording' });
      expect(next).toBe(ready);
    });

    it('ignores recording-finalized outside of stopping', () => {
      const ready = readyState();
      const next = recordingReducer(ready, {
        kind: 'recording-finalized',
        uri: 'file:///tmp/zombie.mp4',
      });
      expect(next).toBe(ready);
      expect(next.lastRecordingUri).toBeNull();
    });
  });

  describe('error and reset', () => {
    it('error from recording clears recordingStartedAt and surfaces the message', () => {
      let s: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'recording',
        permissionGranted: true,
        recordingStartedAt: 12345,
      };
      s = recordingReducer(s, { kind: 'error', message: 'disk full' });
      expect(s.status).toBe('error');
      expect(s.errorMessage).toBe('disk full');
      expect(s.recordingStartedAt).toBeNull();
    });

    it('reset from error returns to ready when permission is still held', () => {
      const errored: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'error',
        permissionGranted: true,
        errorMessage: 'whatever',
      };
      const next = recordingReducer(errored, { kind: 'reset' });
      expect(next.status).toBe('ready');
      expect(next.errorMessage).toBeNull();
    });

    it('reset from error returns to unknown when no permission has been granted', () => {
      const errored: RecordingState = {
        ...INITIAL_RECORDING_STATE,
        status: 'error',
        permissionGranted: false,
        errorMessage: 'whatever',
      };
      const next = recordingReducer(errored, { kind: 'reset' });
      expect(next.status).toBe('unknown');
    });

    it('error does NOT wipe a successful recording URI when it fires on a stale callback', () => {
      const idle: RecordingState = {
        status: 'idle-with-recording',
        lastRecordingUri: 'file:///tmp/keep-me.mp4',
        recordingStartedAt: null,
        errorMessage: null,
        permissionGranted: true,
      };
      const next = recordingReducer(idle, { kind: 'error', message: 'late' });
      // error from idle-with-recording is ignored: the recording already
      // succeeded, a delayed callback must not corrupt it.
      expect(next).toBe(idle);
    });
  });

  describe('convenience selectors', () => {
    it('canStartRecording is true exactly for ready and idle-with-recording', () => {
      const matrix: [RecordingState['status'], boolean][] = [
        ['unknown', false],
        ['permission-pending', false],
        ['permission-denied', false],
        ['ready', true],
        ['recording', false],
        ['stopping', false],
        ['idle-with-recording', true],
        ['error', false],
      ];
      for (const [status, expected] of matrix) {
        const s: RecordingState = { ...INITIAL_RECORDING_STATE, status };
        expect(canStartRecording(s)).toBe(expected);
      }
    });

    it('isActivelyRecording is true only in recording', () => {
      expect(isActivelyRecording({ ...INITIAL_RECORDING_STATE, status: 'recording' })).toBe(true);
      expect(isActivelyRecording({ ...INITIAL_RECORDING_STATE, status: 'stopping' })).toBe(false);
      expect(isActivelyRecording(INITIAL_RECORDING_STATE)).toBe(false);
    });
  });
});
