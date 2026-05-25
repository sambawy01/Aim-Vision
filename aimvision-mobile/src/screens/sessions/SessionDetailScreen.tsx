/**
 * Session detail.
 *
 * Pulls `GET /sessions/{id}` + summary + shots + coaching-note in parallel.
 * Renders an actions block:
 *   - "Record video" → CapturePhone (if flag enabled).
 *   - "End session" → POST /sessions/{id}/end.
 *
 * Coaching-note + shot list are display-only for now; the backend pipeline
 * that populates them lives in workstreams D + E of the production-build
 * plan.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import {
  endSession,
  getCoachingNote,
  getSession,
  getSessionSummary,
  listRecordings,
  listSessionShots,
  type CoachingNote,
  type Recording,
  type Session,
  type SessionSummary,
  type Shot,
} from '../../services/sessions';
import { usePhoneCaptureEnabled } from '../../config/flags';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'SessionDetail'>;
type Route = RouteProp<AppStackParamList, 'SessionDetail'>;

interface Bundle {
  session: Session;
  summary: SessionSummary | null;
  shots: Shot[];
  recordings: Recording[];
  note: CoachingNote | null;
}

export function SessionDetailScreen(): React.ReactElement {
  const route = useRoute<Route>();
  const navigation = useNavigation<Nav>();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const phoneCapture = usePhoneCaptureEnabled();

  const sessionId = route.params.sessionId;
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const session = await getSession(sessionId);
      // The summary/shots/note endpoints are optional and may 404 before the
      // ML pipeline has run — wrap each so the page still renders.
      const [summary, shots, recordings, note] = await Promise.all([
        getSessionSummary(sessionId).catch(() => null),
        listSessionShots(sessionId).catch(() => [] as Shot[]),
        listRecordings(sessionId).catch(() => [] as Recording[]),
        getCoachingNote(sessionId).catch(() => null),
      ]);
      setBundle({ session, summary, shots, recordings, note });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const onEnd = async (): Promise<void> => {
    if (!bundle) return;
    setEnding(true);
    try {
      await endSession(sessionId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setEnding(false);
    }
  };

  if (!bundle) {
    return (
      <View style={[styles.container, styles.center]}>
        {error ? (
          <AccessibleText variant="body" color="danger">
            {error}
          </AccessibleText>
        ) : (
          <ActivityIndicator color={theme.colors.textPrimary} />
        )}
      </View>
    );
  }

  const { session, summary, shots, recordings, note } = bundle;
  const ended = Boolean(session.ended_at);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">{session.discipline}</AccessibleText>
      <AccessibleText variant="caption" color="textSecondary">
        Started {new Date(session.started_at).toLocaleString()}
        {session.ended_at ? ` · ended ${new Date(session.ended_at).toLocaleTimeString()}` : ''}
      </AccessibleText>

      {summary ? (
        <View style={styles.kpis}>
          <Kpi label="Shots" value={String(summary.shot_count)} theme={theme} />
          <Kpi label="Recordings" value={String(summary.recording_count)} theme={theme} />
          <Kpi
            label="Calibration"
            value={summary.calibration_complete ? '✓' : `${summary.calibration_count}`}
            theme={theme}
          />
        </View>
      ) : null}

      <View style={styles.section}>
        <AccessibleText variant="title">Actions</AccessibleText>
        {phoneCapture && !ended ? (
          <Pressable
            style={styles.btn}
            onPress={() => navigation.navigate('CapturePhone', { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Record video"
          >
            <AccessibleText variant="title" color="white">
              ● Record video
            </AccessibleText>
          </Pressable>
        ) : null}
        {!ended ? (
          <Pressable
            style={[styles.btn, styles.btnSecondary, ending && styles.btnDisabled]}
            onPress={onEnd}
            disabled={ending}
            accessibilityRole="button"
            accessibilityLabel="End session"
          >
            <AccessibleText variant="title">{ending ? 'Ending…' : 'End session'}</AccessibleText>
          </Pressable>
        ) : (
          <AccessibleText variant="body" color="textSecondary" style={styles.muted}>
            Session ended. ML pipeline will populate shots + coaching note
            shortly.
          </AccessibleText>
        )}
      </View>

      <View style={styles.section}>
        <AccessibleText variant="title">Recordings</AccessibleText>
        {recordings.length === 0 ? (
          <AccessibleText variant="body" color="textSecondary">
            None yet. Record from the camera to upload one.
          </AccessibleText>
        ) : (
          recordings.map((r) => (
            <Pressable
              key={r.id}
              style={styles.shotRow}
              onPress={() =>
                navigation.navigate('RecordingPlayer', {
                  sessionId,
                  recordingId: r.id,
                })
              }
              accessibilityRole="button"
              accessibilityLabel={`Play recording ${r.id.slice(0, 8)}`}
            >
              <AccessibleText variant="body">
                ▶ {r.source_kind}
                {r.duration_ms !== null ? ` · ${Math.round(r.duration_ms / 1000)}s` : ''} ·{' '}
                {r.upload_state}
              </AccessibleText>
              <AccessibleText variant="caption" color="textMuted">
                {r.id}
              </AccessibleText>
            </Pressable>
          ))
        )}
      </View>

      <View style={styles.section}>
        <AccessibleText variant="title">Shots</AccessibleText>
        {shots.length === 0 ? (
          <AccessibleText variant="body" color="textSecondary">
            No shots yet. The ML pipeline runs after a session ends.
          </AccessibleText>
        ) : (
          shots.map((s) => (
            <View key={s.id} style={styles.shotRow}>
              <AccessibleText variant="body">
                #{s.seq} · t={s.t_ms}ms · {s.outcome}
              </AccessibleText>
            </View>
          ))
        )}
      </View>

      <View style={styles.section}>
        <AccessibleText variant="title">Coaching note</AccessibleText>
        {note ? (
          <View style={styles.note}>
            <AccessibleText variant="body">{note.body}</AccessibleText>
            {note.generated_at ? (
              <AccessibleText
                variant="caption"
                color="textMuted"
                style={{ marginTop: theme.spacing.xs }}
              >
                Generated {new Date(note.generated_at).toLocaleString()}
              </AccessibleText>
            ) : null}
          </View>
        ) : (
          <AccessibleText variant="body" color="textSecondary">
            No coaching note yet.
          </AccessibleText>
        )}
      </View>

      {error ? (
        <AccessibleText variant="body" color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      ) : null}
    </ScrollView>
  );
}

function Kpi({
  label,
  value,
  theme,
}: {
  label: string;
  value: string;
  theme: Theme;
}): React.ReactElement {
  return (
    <View style={{ flex: 1, padding: theme.spacing.md }}>
      <AccessibleText variant="caption" color="textSecondary">
        {label}
      </AccessibleText>
      <AccessibleText variant="display">{value}</AccessibleText>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
    },
    content: {
      padding: theme.spacing.lg,
      paddingBottom: theme.spacing.xxl,
    },
    center: {
      justifyContent: 'center',
      alignItems: 'center',
    },
    kpis: {
      flexDirection: 'row',
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      marginTop: theme.spacing.md,
    },
    section: {
      marginTop: theme.spacing.xl,
    },
    btn: {
      backgroundColor: theme.colors.accent,
      borderRadius: theme.radii.pill,
      paddingVertical: theme.spacing.md,
      alignItems: 'center',
      marginTop: theme.spacing.md,
    },
    btnSecondary: {
      backgroundColor: theme.colors.surface,
    },
    btnDisabled: {
      opacity: 0.5,
    },
    muted: {
      marginTop: theme.spacing.md,
    },
    shotRow: {
      padding: theme.spacing.sm,
      borderBottomColor: theme.colors.border,
      borderBottomWidth: StyleSheet.hairlineWidth,
    },
    note: {
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      marginTop: theme.spacing.sm,
    },
    error: {
      marginTop: theme.spacing.md,
    },
  });
}
