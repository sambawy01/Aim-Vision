import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { useFlag } from '../../hooks/useFlag';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { colors, spacing, radii } from '../../theme/tokens';

// Gate name is the contract with Statsig — keep stable across versions or
// migrate explicitly. Default to `false` so an uninitialized client / dropped
// SDK / offline state never silently exposes preview UI.
const DIAGNOSTIC_BANNER_FLAG = 'home_diagnostic_banner_v1';

export function HomeScreen(): React.ReactElement {
  const { t } = useTranslation();
  const showDiagnosticBanner = useFlag(DIAGNOSTIC_BANNER_FLAG, false);
  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('home.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        {t('home.noSessions')}
      </AccessibleText>
      {showDiagnosticBanner ? (
        <View style={styles.banner} testID="home-diagnostic-banner">
          <AccessibleText variant="title">
            {t('home.diagnosticBanner.title')}
          </AccessibleText>
          <AccessibleText variant="body" color="textSecondary" style={styles.body}>
            {t('home.diagnosticBanner.body')}
          </AccessibleText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.lg,
  },
  body: {
    marginTop: spacing.md,
  },
  banner: {
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
  },
});
