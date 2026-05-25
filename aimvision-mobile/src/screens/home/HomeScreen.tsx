/**
 * Sessions list — the post-login landing screen.
 *
 * Pulls `GET /sessions` and renders each as a tap-to-detail row. A floating
 * "New session" button opens the creation flow. Pull-to-refresh hits the same
 * endpoint to refresh after returning from create/end.
 *
 * Listed as the "Home" tab/route to match `AppStackParamList` (kept that name
 * for backward-compat with the existing nav types; the human-facing label in
 * `TabBar.tsx` is "Sessions").
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import { listSessions, type Session } from '../../services/sessions';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'Home'>;

export function HomeScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // Initial load + reload on every refocus (covers returning from create flow).
  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  useEffect(() => {
    void load();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <AccessibleText variant="display">Sessions</AccessibleText>
      </View>

      {error ? (
        <AccessibleText variant="body" color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      ) : null}

      <FlatList
        data={sessions ?? []}
        keyExtractor={(s) => s.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => navigation.navigate('SessionDetail', { sessionId: item.id })}
            accessibilityRole="button"
            accessibilityLabel={`Open session ${item.id}`}
          >
            <View style={{ flex: 1 }}>
              <AccessibleText variant="title">{item.discipline}</AccessibleText>
              <AccessibleText variant="caption" color="textSecondary">
                {new Date(item.started_at).toLocaleString()}
                {item.ended_at ? ' · ended' : ' · in progress'}
              </AccessibleText>
            </View>
            <AccessibleText variant="title" color="textMuted">
              ›
            </AccessibleText>
          </Pressable>
        )}
        ListEmptyComponent={
          sessions === null ? (
            <AccessibleText variant="body" color="textSecondary">
              Loading…
            </AccessibleText>
          ) : (
            <View style={styles.empty}>
              <AccessibleText variant="title">No sessions yet</AccessibleText>
              <AccessibleText
                variant="body"
                color="textSecondary"
                style={{ marginTop: theme.spacing.sm }}
              >
                Tap "New session" to record your first run.
              </AccessibleText>
            </View>
          )
        }
      />

      <Pressable
        style={styles.fab}
        onPress={() => navigation.navigate('NewSession')}
        accessibilityRole="button"
        accessibilityLabel="New session"
      >
        <AccessibleText variant="title" color="white">
          + New session
        </AccessibleText>
      </Pressable>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
    },
    header: {
      padding: theme.spacing.lg,
      paddingBottom: theme.spacing.sm,
    },
    list: {
      padding: theme.spacing.lg,
      paddingTop: theme.spacing.sm,
      paddingBottom: 96,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.sm,
    },
    empty: {
      padding: theme.spacing.lg,
      alignItems: 'flex-start',
    },
    error: {
      paddingHorizontal: theme.spacing.lg,
    },
    fab: {
      position: 'absolute',
      bottom: theme.spacing.lg,
      right: theme.spacing.lg,
      left: theme.spacing.lg,
      backgroundColor: theme.colors.accent,
      borderRadius: theme.radii.pill,
      paddingVertical: theme.spacing.md,
      alignItems: 'center',
    },
  });
}
