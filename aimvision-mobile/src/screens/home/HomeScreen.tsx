import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { useFlag } from '../../hooks/useFlag';
import { useRangeMode } from '../../components/RangeMode';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import type { Theme } from '../../theme/tokens';

// Gate name is the contract with Statsig — keep stable across versions or
// migrate explicitly. Default to `false` so an uninitialized client / dropped
// SDK / offline state never silently exposes preview UI.
const DIAGNOSTIC_BANNER_FLAG = 'home_diagnostic_banner_v1';

export function HomeScreen(): React.ReactElement {
  const { t } = useTranslation();
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const showDiagnosticBanner = useFlag(DIAGNOSTIC_BANNER_FLAG, false);
  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('home.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        {t('home.noSessions')}
      </AccessibleText>
      {showDiagnosticBanner ? (
        <View style={styles.banner} testID="home-diagnostic-banner">
          <AccessibleText variant="title">{t('home.diagnosticBanner.title')}</AccessibleText>
          <AccessibleText variant="body" color="textSecondary" style={styles.body}>
            {t('home.diagnosticBanner.body')}
          </AccessibleText>
        </View>
      ) : null}
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.bg,
      padding: theme.spacing.lg,
    },
    body: {
      marginTop: theme.spacing.md,
    },
    banner: {
      marginTop: theme.spacing.lg,
      padding: theme.spacing.md,
      borderRadius: theme.radii.md,
      backgroundColor: theme.colors.surface,
    },
  });
}
