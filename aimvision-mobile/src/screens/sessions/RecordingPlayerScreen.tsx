/**
 * Recording playback screen.
 *
 * The backend's `RecordingOut.storage_uri` points at server-side storage
 * (local-fs path in this staging deploy, S3/MinIO in production). Without
 * a public-URL download endpoint, native iOS can't stream it directly.
 *
 * For Phase 1 the player tries the storage_uri verbatim — works if it's
 * a `file://` (local capture, e.g. when running against the dev backend on
 * the same Mac) or a public URL. When playback fails we surface the URI
 * and the error so the user knows it's a known limitation (the streaming
 * download endpoint is workstream B's follow-up).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { useRoute, type RouteProp } from '@react-navigation/native';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useEvent } from 'expo';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import { getSession, type Recording } from '../../services/sessions';
import { api } from '../../services/api';
import type { AppStackParamList } from '../../navigation/types';

type Route = RouteProp<AppStackParamList, 'RecordingPlayer'>;

export function RecordingPlayerScreen(): React.ReactElement {
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const route = useRoute<Route>();
  const { sessionId, recordingId } = route.params;

  const [recording, setRecording] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        // The single-recording GET returns the same shape as the list.
        const rec = await api<Recording>(`/sessions/${sessionId}/recording/${recordingId}`);
        // Defensive: backend may return a session reference too; we
        // don't need it, but keep the call to surface obvious 404s.
        await getSession(sessionId);
        if (alive) setRecording(rec);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [sessionId, recordingId]);

  // Always create the player (hooks must be called unconditionally) — pass
  // null when we don't have a URI yet so it stays in a no-source state.
  const sourceUri = recording?.storage_uri ?? null;
  const player = useVideoPlayer(sourceUri, (p) => {
    p.loop = false;
    p.muted = false;
  });

  const { status, error: playbackError } = useEvent(player, 'statusChange', {
    status: player.status,
    error: undefined,
  });

  if (error) {
    return (
      <View style={[styles.container, styles.center]}>
        <AccessibleText variant="body" color="danger">
          {error}
        </AccessibleText>
      </View>
    );
  }
  if (!recording) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={theme.colors.textPrimary} />
      </View>
    );
  }

  const looksPlayable =
    recording.storage_uri.startsWith('http://') ||
    recording.storage_uri.startsWith('https://') ||
    recording.storage_uri.startsWith('file://');

  return (
    <View style={styles.container}>
      <View style={styles.playerWrap}>
        {looksPlayable ? (
          <VideoView style={styles.player} player={player} contentFit="contain" />
        ) : (
          <View style={[styles.player, styles.center]}>
            <AccessibleText variant="title" color="textSecondary">
              ⏵
            </AccessibleText>
            <AccessibleText
              variant="bodySmall"
              color="textMuted"
              style={{ marginTop: theme.spacing.sm, textAlign: 'center' }}
            >
              storage_uri is server-internal (`{recording.storage_uri.slice(0, 32)}…`).
              Streaming-download endpoint lands with the cloud-storage rollout.
            </AccessibleText>
          </View>
        )}
      </View>

      <View style={styles.meta}>
        <AccessibleText variant="title">{recording.source_kind}</AccessibleText>
        <AccessibleText variant="caption" color="textSecondary">
          {recording.duration_ms !== null
            ? `${Math.round(recording.duration_ms / 1000)}s`
            : 'unknown duration'}{' '}
          · {recording.upload_state}
        </AccessibleText>
        {recording.sha256 ? (
          <AccessibleText variant="caption" color="textMuted">
            sha256: {recording.sha256.slice(0, 16)}…
          </AccessibleText>
        ) : null}
        <AccessibleText
          variant="caption"
          color={
            playbackError
              ? 'danger'
              : status === 'readyToPlay'
                ? 'success'
                : 'textMuted'
          }
        >
          player: {status}
          {playbackError ? ` — ${String(playbackError)}` : ''}
        </AccessibleText>
      </View>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
    },
    center: {
      alignItems: 'center',
      justifyContent: 'center',
    },
    playerWrap: {
      backgroundColor: theme.colors.black,
      aspectRatio: 16 / 9,
      width: '100%',
    },
    player: {
      width: '100%',
      height: '100%',
    },
    meta: {
      padding: theme.spacing.lg,
      gap: theme.spacing.xs,
    },
  });
}
