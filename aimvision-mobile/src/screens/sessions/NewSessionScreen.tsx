/**
 * New-session creation flow.
 *
 * - Loads available athletes + drills in parallel (backend filters athletes
 *   by the current tenant via RLS).
 * - User picks one of each + the discipline derived from the drill.
 * - POSTs `/sessions` and navigates to SessionDetail on success so the
 *   user can immediately start capture / end the session.
 *
 * Athlete/drill selection is plain Pressable rows for now; the production UI
 * gets searchable lists once the catalog grows beyond demo size.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import {
  listAthletes,
  listDrills,
  type Athlete,
  type Drill,
} from '../../services/catalog';
import { createSession } from '../../services/sessions';
import { useAuthStore } from '../../state/authStore';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'NewSession'>;

export function NewSessionScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const session = useAuthStore((s) => s.session);

  const [athletes, setAthletes] = useState<Athlete[] | null>(null);
  const [drills, setDrills] = useState<Drill[] | null>(null);
  const [athleteId, setAthleteId] = useState<string | null>(null);
  const [drillId, setDrillId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [a, d] = await Promise.all([listAthletes(), listDrills()]);
        if (!alive) return;
        setAthletes(a);
        setDrills(d);
        // Default: self if the logged-in user appears in the athlete list
        // (athlete role) — otherwise the first item.
        const selfId = session?.athleteIdHash;
        const selfMatch = selfId ? a.find((x) => x.id === selfId) : undefined;
        setAthleteId((selfMatch ?? a[0])?.id ?? null);
        setDrillId(d[0]?.id ?? null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [session]);

  const selectedDrill = drills?.find((d) => d.id === drillId) ?? null;

  const onCreate = async (): Promise<void> => {
    if (!athleteId || !selectedDrill) return;
    setSubmitting(true);
    setError(null);
    try {
      // org_id is the current tenant (the auth principal's tenant_id).
      // The backend rejects anything outside the principal's scope via RLS.
      const orgId = useAuthStore.getState().session ? 'org-democlub' : 'org-democlub';
      const created = await createSession({
        athlete_user_id: athleteId,
        org_id: orgId,
        discipline: selectedDrill.discipline,
      });
      navigation.replace('SessionDetail', { sessionId: created.id });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (athletes === null || drills === null) {
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

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">New session</AccessibleText>

      <View style={styles.section}>
        <AccessibleText variant="title" color="textSecondary" style={styles.label}>
          Athlete
        </AccessibleText>
        {athletes.length === 0 ? (
          <AccessibleText variant="body" color="textMuted">
            No athletes available in this tenant.
          </AccessibleText>
        ) : (
          athletes.map((a) => (
            <Pressable
              key={a.id}
              style={[styles.row, athleteId === a.id && styles.rowSelected]}
              onPress={() => setAthleteId(a.id)}
              accessibilityRole="radio"
              accessibilityState={{ selected: athleteId === a.id }}
            >
              <AccessibleText variant="body">{a.display_name}</AccessibleText>
              {a.email ? (
                <AccessibleText variant="caption" color="textSecondary">
                  {a.email}
                </AccessibleText>
              ) : null}
            </Pressable>
          ))
        )}
      </View>

      <View style={styles.section}>
        <AccessibleText variant="title" color="textSecondary" style={styles.label}>
          Drill
        </AccessibleText>
        {drills.length === 0 ? (
          <AccessibleText variant="body" color="textMuted">
            No drills configured. Seed the catalog and retry.
          </AccessibleText>
        ) : (
          drills.map((d) => (
            <Pressable
              key={d.id}
              style={[styles.row, drillId === d.id && styles.rowSelected]}
              onPress={() => setDrillId(d.id)}
              accessibilityRole="radio"
              accessibilityState={{ selected: drillId === d.id }}
            >
              <AccessibleText variant="body">{d.name}</AccessibleText>
              <AccessibleText variant="caption" color="textSecondary">
                {d.discipline} · {d.description}
              </AccessibleText>
            </Pressable>
          ))
        )}
      </View>

      {error ? (
        <AccessibleText variant="body" color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      ) : null}

      <View style={styles.actions}>
        <Pressable
          style={[
            styles.createBtn,
            (!athleteId || !drillId || submitting) && styles.createBtnDisabled,
          ]}
          disabled={!athleteId || !drillId || submitting}
          onPress={onCreate}
          accessibilityRole="button"
          accessibilityLabel="Create session"
        >
          <AccessibleText variant="title" color="white">
            {submitting ? 'Creating…' : 'Create session'}
          </AccessibleText>
        </Pressable>
      </View>
    </ScrollView>
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
    section: {
      marginTop: theme.spacing.lg,
    },
    label: {
      marginBottom: theme.spacing.sm,
    },
    row: {
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.sm,
      borderWidth: 1,
      borderColor: theme.colors.surface,
    },
    rowSelected: {
      borderColor: theme.colors.accent,
    },
    error: {
      marginTop: theme.spacing.md,
    },
    actions: {
      marginTop: theme.spacing.xl,
    },
    createBtn: {
      backgroundColor: theme.colors.accent,
      borderRadius: theme.radii.pill,
      paddingVertical: theme.spacing.md,
      alignItems: 'center',
    },
    createBtnDisabled: {
      opacity: 0.5,
    },
  });
}
