/**
 * Per-athlete detail + progress.
 *
 * Pulls `GET /athletes/{id}` + `GET /athletes/{id}/progress` in parallel
 * and renders:
 *   - identity (display name + email + joined date)
 *   - high-level KPIs (sessions analyzed)
 *   - per-diagnostic-chip delta vs. baseline (positive = improvement)
 *   - the last N analysed sessions with shot count + chip badges
 */
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import {
  getAthlete,
  getAthleteProgress,
  type Athlete,
  type AthleteProgress,
} from '../../services/catalog';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'AthleteDetail'>;
type Route = RouteProp<AppStackParamList, 'AthleteDetail'>;

export function AthleteDetailScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const athleteId = route.params.athleteId;
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [progress, setProgress] = useState<AthleteProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [a, p] = await Promise.all([
          getAthlete(athleteId),
          getAthleteProgress(athleteId).catch(() => null),
        ]);
        if (!alive) return;
        setAthlete(a);
        setProgress(p);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [athleteId]);

  if (error) {
    return (
      <View style={[styles.container, styles.center]}>
        <AccessibleText variant="body" color="danger">
          {error}
        </AccessibleText>
      </View>
    );
  }
  if (!athlete) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={theme.colors.textPrimary} />
      </View>
    );
  }

  const deltaEntries = progress ? Object.entries(progress.deltas) : [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">{athlete.display_name}</AccessibleText>
      {athlete.email ? (
        <AccessibleText variant="caption" color="textSecondary">
          {athlete.email}
        </AccessibleText>
      ) : null}
      <AccessibleText variant="caption" color="textMuted">
        Joined {new Date(athlete.joined_at).toLocaleDateString()}
      </AccessibleText>

      <View style={styles.section}>
        <AccessibleText variant="title">Progress</AccessibleText>
        {progress ? (
          <>
            <View style={styles.kpis}>
              <View style={styles.kpi}>
                <AccessibleText variant="caption" color="textSecondary">
                  Sessions analysed
                </AccessibleText>
                <AccessibleText variant="display">
                  {progress.sessions_analyzed}
                </AccessibleText>
              </View>
            </View>
            {deltaEntries.length > 0 ? (
              <View style={styles.deltas}>
                {deltaEntries.map(([k, v]) => (
                  <View key={k} style={styles.deltaRow}>
                    <AccessibleText variant="body">{k}</AccessibleText>
                    <AccessibleText
                      variant="title"
                      color={v > 0 ? 'success' : v < 0 ? 'danger' : 'textMuted'}
                    >
                      {v > 0 ? '+' : ''}
                      {v.toFixed(2)}
                    </AccessibleText>
                  </View>
                ))}
              </View>
            ) : null}
          </>
        ) : (
          <AccessibleText variant="body" color="textSecondary">
            No analysed sessions yet.
          </AccessibleText>
        )}
      </View>

      {progress && progress.sessions.length > 0 ? (
        <View style={styles.section}>
          <AccessibleText variant="title">Recent sessions</AccessibleText>
          {progress.sessions.map((s) => (
            <Pressable
              key={s.session_id}
              style={styles.sessionRow}
              onPress={() =>
                navigation.navigate('SessionDetail', { sessionId: s.session_id })
              }
              accessibilityRole="button"
              accessibilityLabel="Open session"
            >
              <AccessibleText variant="body">
                {new Date(s.started_at).toLocaleString()}
              </AccessibleText>
              <AccessibleText variant="caption" color="textSecondary">
                {s.shot_count} shots
                {s.diagnostic_chips.length > 0
                  ? ` · ${s.diagnostic_chips.slice(0, 3).join(', ')}${s.diagnostic_chips.length > 3 ? '…' : ''}`
                  : ''}
              </AccessibleText>
            </Pressable>
          ))}
        </View>
      ) : null}
    </ScrollView>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.bg },
    content: { padding: theme.spacing.lg, paddingBottom: theme.spacing.xxl },
    center: { alignItems: 'center', justifyContent: 'center' },
    section: { marginTop: theme.spacing.xl, gap: theme.spacing.sm },
    kpis: {
      flexDirection: 'row',
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
    },
    kpi: { flex: 1 },
    deltas: {
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    deltaRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    sessionRow: {
      padding: theme.spacing.md,
      borderBottomColor: theme.colors.border,
      borderBottomWidth: StyleSheet.hairlineWidth,
    },
  });
}
