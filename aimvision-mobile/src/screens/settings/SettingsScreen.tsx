import React, { useMemo, useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import { useAuthStore } from '../../state/authStore';
import { logout } from '../../services/auth';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'Settings'>;

export function SettingsScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  const { inRangeMode, setManualOverride, theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const session = useAuthStore((s) => s.session);
  const [signingOut, setSigningOut] = useState(false);

  const rangeModeLabel = `${t('settings.rangeMode')} · ${
    inRangeMode ? t('common.on') : t('common.off')
  }`;

  const onSignOut = (): void => {
    Alert.alert('Sign out?', 'You will need to sign in again to use the app.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          setSigningOut(true);
          try {
            await logout();
            // RootNavigator subscribes to the auth store; clearing the
            // token swaps AuthStack back in reactively.
          } catch {
            // logout() swallows the backend error and clears local state
            // anyway, so we always land logged-out.
          } finally {
            setSigningOut(false);
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('settings.title')}</AccessibleText>

      {session ? (
        <View style={styles.profile}>
          <AccessibleText variant="caption" color="textSecondary">
            Signed in
          </AccessibleText>
          <AccessibleText variant="title">
            {session.email ?? session.athleteIdHash.slice(0, 12)}
          </AccessibleText>
          <AccessibleText variant="caption" color="textMuted">
            {session.ageGroup}
            {session.parentLinked ? ' · parent linked' : ''}
          </AccessibleText>
        </View>
      ) : null}

      <AccessibleTouchable
        accessibilityLabel={t('settings.dataPrivacy')}
        onPress={() => navigation.navigate('DataPrivacy')}
        style={styles.row}
      >
        <AccessibleText variant="body">{t('settings.dataPrivacy')}</AccessibleText>
      </AccessibleTouchable>

      <AccessibleTouchable
        accessibilityLabel={rangeModeLabel}
        accessibilityState={{ checked: inRangeMode }}
        onPress={() => setManualOverride(inRangeMode ? false : true)}
        style={styles.row}
        testID="settings-range-mode-toggle"
      >
        <AccessibleText variant="body">{t('settings.rangeMode')}</AccessibleText>
        <AccessibleText
          variant="bodySmall"
          color={inRangeMode ? 'accent' : 'textMuted'}
          style={styles.indicator}
        >
          {inRangeMode ? t('common.on') : t('common.off')}
        </AccessibleText>
      </AccessibleTouchable>

      <AccessibleTouchable
        accessibilityLabel="Sign out"
        onPress={onSignOut}
        style={
          signingOut
            ? [styles.row, styles.signOutRow, styles.rowDisabled]
            : [styles.row, styles.signOutRow]
        }
        disabled={signingOut}
        testID="settings-sign-out"
      >
        <AccessibleText variant="body" color="danger">
          {signingOut ? 'Signing out…' : 'Sign out'}
        </AccessibleText>
      </AccessibleTouchable>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
      padding: theme.spacing.lg,
      gap: theme.spacing.md,
    },
    row: {
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.md,
      borderRadius: theme.radii.md,
      backgroundColor: theme.colors.surface,
      borderWidth: 1,
      borderColor: theme.colors.border,
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      minHeight: theme.tapTargets.minimum,
    },
    indicator: {
      marginLeft: theme.spacing.md,
    },
    profile: {
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      gap: theme.spacing.xs,
    },
    signOutRow: {
      marginTop: theme.spacing.lg,
      borderColor: theme.colors.danger,
    },
    rowDisabled: {
      opacity: 0.5,
    },
  });
}
