import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
  useFrameProcessor,
  useMicrophonePermission,
  VisionCameraProxy,
} from 'react-native-vision-camera';
import { useRoute, type RouteProp } from '@react-navigation/native';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import {
  canStartRecording,
  INITIAL_RECORDING_STATE,
  recordingReducer,
} from '../../capture/phoneRecordingState';
import { formatFps, formatResolution } from '../../capture/frameStats';
import { useFrameStats } from '../../capture/useFrameStats';
import { uploadRecording } from '../../services/sessions';
import type { AppStackParamList } from '../../navigation/types';

type Route = RouteProp<AppStackParamList, 'CapturePhone'>;
type UploadState =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'uploaded'; recordingId: string }
  | { kind: 'failed'; message: string };

/**
 * Sprint 4 dev-mode phone capture screen — ADR-0009 slice 1.
 *
 * Records to a local MP4 via `react-native-vision-camera`'s built-in
 * `recordVideo`. No frame processor yet (that's slice 3). No backend
 * upload yet (that's slice 2). The recording state machine in
 * `src/capture/phoneRecordingState.ts` is the source of truth; this
 * screen forwards UI actions and Vision Camera callbacks into events.
 */
export function CapturePhoneScreen(): React.ReactElement {
  const { t } = useTranslation();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  // Optional sessionId from the route: when the user came from
  // SessionDetail's "Record video" CTA, finishing a recording auto-
  // uploads it as part of that session. When the user entered Capture
  // via the bottom tab without a session, recordings stay local-only.
  const route = useRoute<Route>();
  const routeSessionId = route.params?.sessionId;

  const [state, dispatch] = useReducer(recordingReducer, INITIAL_RECORDING_STATE);
  const [upload, setUpload] = useState<UploadState>({ kind: 'idle' });

  const device = useCameraDevice('back');
  const cameraPerm = useCameraPermission();
  const micPerm = useMicrophonePermission();
  const cameraRef = useRef<Camera>(null);

  // Frame-processor pipeline (ADR-0009 slice 3a + 3b). The worklet runs on
  // the camera thread per Vision Camera v4 + worklets-core; it writes
  // through the shared values, the screen polls them via `useFrameStats`.
  //
  // Slice 3b adds a native plugin call: when the `avPhoneFrameSink`
  // native plugin is registered (after `expo prebuild` has copied the
  // Swift/Kotlin sources via `plugins/phone-frame-sink/`), the worklet
  // invokes it per-frame and writes the native-reported source into
  // `lastSourceTag` so the on-screen banner can show "native-ios" /
  // "native-android" vs. the slice-3a JS fallback "js-worklet". If the
  // plugin isn't registered (i.e. before prebuild, or in a future build
  // that opts out), the worklet keeps doing slice-3a metadata.
  const { stats: frameStats, sharedValues } = useFrameStats();
  const nativeFrameSink = useMemo(
    () => VisionCameraProxy.initFrameProcessorPlugin('avPhoneFrameSink', {}),
    [],
  );
  const frameProcessor = useFrameProcessor(
    (frame) => {
      'worklet';
      sharedValues.frameCount.value = sharedValues.frameCount.value + 1;
      sharedValues.lastTimestampNs.value = frame.timestamp;
      sharedValues.lastWidth.value = frame.width;
      sharedValues.lastHeight.value = frame.height;
      sharedValues.lastPixelFormat.value = frame.pixelFormat;

      if (nativeFrameSink != null) {
        const result = nativeFrameSink.call(frame);
        if (result != null && typeof result === 'object' && 'source' in result) {
          sharedValues.lastSourceTag.value = String(result.source);
        }
      } else {
        sharedValues.lastSourceTag.value = 'js-worklet';
      }
    },
    [sharedValues, nativeFrameSink],
  );

  // Reflect the OS permission state into the state machine on every
  // change. Both camera AND microphone must be granted before we treat
  // the user as "ready"; phones grant them in separate prompts.
  useEffect(() => {
    if (state.status !== 'permission-pending') return;
    if (cameraPerm.hasPermission && micPerm.hasPermission) {
      dispatch({ kind: 'permission-granted' });
    } else if (!cameraPerm.hasPermission && state.permissionGranted === false) {
      // If the OS already returned a decision (`requestPermission` resolved)
      // and a permission is still missing, treat that as a denial. We
      // err on the side of staying in `permission-pending` until the OS
      // settles — the deny event arrives via the requestPermission
      // promise below.
    }
  }, [state.status, state.permissionGranted, cameraPerm.hasPermission, micPerm.hasPermission]);

  const requestPermissions = useCallback(async () => {
    dispatch({ kind: 'request-permission' });
    const [cam, mic] = await Promise.all([
      cameraPerm.requestPermission(),
      micPerm.requestPermission(),
    ]);
    if (cam && mic) {
      dispatch({ kind: 'permission-granted' });
    } else {
      dispatch({
        kind: 'permission-denied',
        reason: !cam ? 'camera' : 'microphone',
      });
    }
  }, [cameraPerm, micPerm]);

  const startRecording = useCallback(async () => {
    if (!canStartRecording(state)) return;
    if (!device) {
      dispatch({ kind: 'error', message: t('capturePhone.noCamera') });
      return;
    }
    dispatch({ kind: 'start-recording' });
    cameraRef.current?.startRecording({
      fileType: 'mp4',
      onRecordingFinished: (video) => {
        dispatch({ kind: 'recording-finalized', uri: video.path });
      },
      onRecordingError: (error) => {
        dispatch({ kind: 'error', message: error.message });
      },
    });
    // `recording-started` is dispatched after the native callback would
    // normally fire — Vision Camera doesn't give us a "did start"
    // callback distinct from the synchronous startRecording call, so we
    // stamp the time ourselves here. The wall-clock value is best-effort
    // and lives in the state purely for UI ("Recording for 12s").
    dispatch({ kind: 'recording-started', at: Date.now() });
  }, [state, device, t]);

  const stopRecording = useCallback(async () => {
    if (state.status !== 'recording') return;
    dispatch({ kind: 'stop-recording' });
    try {
      await cameraRef.current?.stopRecording();
      // The actual file URI arrives via `onRecordingFinished`, not from
      // the awaited stopRecording promise — we leave the state in
      // `stopping` until that callback runs.
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'unknown error';
      dispatch({ kind: 'error', message });
    }
  }, [state.status]);

  const reset = useCallback(() => {
    dispatch({ kind: 'reset' });
    setUpload({ kind: 'idle' });
  }, []);

  // Auto-upload when a recording finishes AND we came from a session.
  // `state.lastRecordingUri` flips from null → URI when vision-camera's
  // `onRecordingFinished` fires. The dependency on `routeSessionId`
  // means a recording started without a session won't accidentally
  // upload when the user navigates here later with one.
  const lastUri = state.lastRecordingUri;
  useEffect(() => {
    if (!routeSessionId || !lastUri) return;
    if (upload.kind !== 'idle') return;
    let cancelled = false;
    setUpload({ kind: 'uploading' });
    (async () => {
      try {
        const rec = await uploadRecording(routeSessionId, {
          fileUri: lastUri,
          sourceKind: 'phone_dev',
        });
        if (cancelled) return;
        setUpload({ kind: 'uploaded', recordingId: rec.id });
      } catch (e) {
        if (cancelled) return;
        const message = e instanceof Error ? e.message : String(e);
        setUpload({ kind: 'failed', message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [lastUri, routeSessionId, upload.kind]);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <AccessibleText variant="display">{t('capturePhone.title')}</AccessibleText>
      <AccessibleText variant="bodySmall" color="textMuted" style={styles.subtitle}>
        {t('capturePhone.subtitle')}
      </AccessibleText>

      {state.permissionGranted && device ? (
        <View style={styles.preview} testID="capture-phone-preview">
          <Camera
            ref={cameraRef}
            style={StyleSheet.absoluteFill}
            device={device}
            isActive={true}
            video={true}
            audio={true}
            frameProcessor={frameProcessor}
          />
        </View>
      ) : null}

      <View style={styles.statusRow}>
        <AccessibleText variant="body" testID="capture-phone-status">
          {renderStatusLabel(state, t)}
        </AccessibleText>
      </View>

      {routeSessionId ? (
        <View style={styles.statusRow}>
          <AccessibleText
            variant="bodySmall"
            color={upload.kind === 'failed' ? 'danger' : 'textSecondary'}
            testID="capture-phone-upload-status"
          >
            {upload.kind === 'idle' && 'Will auto-upload to session when recording stops.'}
            {upload.kind === 'uploading' && 'Uploading to backend…'}
            {upload.kind === 'uploaded' &&
              `Uploaded ✓ (recording ${upload.recordingId.slice(0, 8)}…)`}
            {upload.kind === 'failed' && `Upload failed: ${upload.message}`}
          </AccessibleText>
        </View>
      ) : null}

      {state.permissionGranted ? (
        <View style={styles.statsRow} testID="capture-phone-frame-stats">
          <AccessibleText variant="bodySmall" color="textMuted">
            {t('capturePhone.stats.label', {
              fps: formatFps(frameStats.fps),
              count: frameStats.frameCount,
              resolution: formatResolution(frameStats.resolution),
              format: frameStats.pixelFormat ?? '—',
            })}
          </AccessibleText>
          <AccessibleText variant="caption" color="textMuted">
            {t('capturePhone.stats.source', {
              source: frameStats.sourceTag ?? 'pending…',
            })}
          </AccessibleText>
        </View>
      ) : null}

      <View style={styles.actions}>
        {state.status === 'unknown' || state.status === 'permission-denied' ? (
          <AccessibleTouchable
            accessibilityLabel={t('capturePhone.action.requestPermission')}
            onPress={requestPermissions}
            variant="primary"
            style={styles.primaryBtn}
            testID="capture-phone-request-permission"
          >
            <AccessibleText variant="body" color="white">
              {t('capturePhone.action.requestPermission')}
            </AccessibleText>
          </AccessibleTouchable>
        ) : null}

        {canStartRecording(state) ? (
          <AccessibleTouchable
            accessibilityLabel={t('capturePhone.action.startRecording')}
            onPress={startRecording}
            variant="primary"
            style={styles.primaryBtn}
            testID="capture-phone-start"
          >
            <AccessibleText variant="body" color="white">
              {t('capturePhone.action.startRecording')}
            </AccessibleText>
          </AccessibleTouchable>
        ) : null}

        {state.status === 'recording' ? (
          <AccessibleTouchable
            accessibilityLabel={t('capturePhone.action.stopRecording')}
            onPress={stopRecording}
            variant="primary"
            style={styles.primaryBtn}
            testID="capture-phone-stop"
          >
            <AccessibleText variant="body" color="white">
              {t('capturePhone.action.stopRecording')}
            </AccessibleText>
          </AccessibleTouchable>
        ) : null}

        {state.status === 'error' ? (
          <AccessibleTouchable
            accessibilityLabel={t('capturePhone.action.reset')}
            onPress={reset}
            style={styles.secondaryBtn}
            testID="capture-phone-reset"
          >
            <AccessibleText variant="body">{t('capturePhone.action.reset')}</AccessibleText>
          </AccessibleTouchable>
        ) : null}
      </View>
    </ScrollView>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function renderStatusLabel(state: ReturnType<typeof recordingReducer>, t: TFn): string {
  switch (state.status) {
    case 'unknown':
      return t('capturePhone.status.unknown');
    case 'permission-pending':
      return t('capturePhone.status.permissionPending');
    case 'permission-denied':
      return t('capturePhone.status.permissionDenied');
    case 'ready':
      return t('capturePhone.status.ready');
    case 'recording':
      return t('capturePhone.status.recording');
    case 'stopping':
      return t('capturePhone.status.stopping');
    case 'idle-with-recording':
      return t('capturePhone.status.idleWithRecording', {
        uri: state.lastRecordingUri ?? '',
      });
    case 'error':
      return t('capturePhone.status.error', { message: state.errorMessage ?? '' });
  }
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
    },
    content: {
      padding: theme.spacing.lg,
      // Bottom space so the record button clears the persistent TabBar
      // (~80pt including safe-area inset on a notch device).
      paddingBottom: theme.spacing.xxl * 2,
      gap: theme.spacing.md,
    },
    subtitle: {
      marginTop: -theme.spacing.sm,
    },
    preview: {
      width: '100%',
      aspectRatio: 9 / 16,
      borderRadius: theme.radii.md,
      backgroundColor: theme.colors.surface,
      overflow: 'hidden',
    },
    statusRow: {
      paddingVertical: theme.spacing.sm,
    },
    statsRow: {
      paddingVertical: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
      borderRadius: theme.radii.sm,
      backgroundColor: theme.colors.surface,
    },
    actions: {
      gap: theme.spacing.md,
    },
    primaryBtn: {
      backgroundColor: theme.colors.accent,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      borderRadius: theme.radii.md,
      alignItems: 'center',
      minHeight: theme.tapTargets.primary,
    },
    secondaryBtn: {
      backgroundColor: theme.colors.surface,
      borderWidth: 1,
      borderColor: theme.colors.border,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      borderRadius: theme.radii.md,
      alignItems: 'center',
      minHeight: theme.tapTargets.minimum,
    },
  });
}
