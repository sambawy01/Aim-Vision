/**
 * Athletes list — coach view shows everyone in the tenant; athlete view
 * shows only themselves (backend RLS filters). Tapping a row navigates
 * to the per-athlete progress detail.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import { listAthletes, type Athlete } from '../../services/catalog';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'Athletes'>;

export function AthletesScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const [athletes, setAthletes] = useState<Athlete[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setAthletes(await listAthletes());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

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
        <AccessibleText variant="display">Athletes</AccessibleText>
      </View>
      {error ? (
        <AccessibleText variant="body" color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      ) : null}
      <FlatList
        data={athletes ?? []}
        keyExtractor={(a) => a.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => navigation.navigate('AthleteDetail', { athleteId: item.id })}
            accessibilityRole="button"
            accessibilityLabel={`Open ${item.display_name}`}
          >
            <View style={{ flex: 1 }}>
              <AccessibleText variant="title">{item.display_name}</AccessibleText>
              {item.email ? (
                <AccessibleText variant="caption" color="textSecondary">
                  {item.email}
                </AccessibleText>
              ) : null}
              <AccessibleText variant="caption" color="textMuted">
                Joined {new Date(item.joined_at).toLocaleDateString()}
              </AccessibleText>
            </View>
            <AccessibleText variant="title" color="textMuted">
              ›
            </AccessibleText>
          </Pressable>
        )}
        ListEmptyComponent={
          athletes === null ? (
            <AccessibleText variant="body" color="textSecondary" style={styles.empty}>
              Loading…
            </AccessibleText>
          ) : (
            <AccessibleText variant="body" color="textSecondary" style={styles.empty}>
              No athletes in this tenant yet.
            </AccessibleText>
          )
        }
      />
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.bg },
    header: { padding: theme.spacing.lg, paddingBottom: theme.spacing.sm },
    list: { padding: theme.spacing.lg, paddingTop: theme.spacing.sm, paddingBottom: 96 },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.sm,
    },
    empty: { padding: theme.spacing.lg },
    error: { paddingHorizontal: theme.spacing.lg },
  });
}
