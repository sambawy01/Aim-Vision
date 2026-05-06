import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { colors, spacing } from '../../theme/tokens';

export function HomeScreen(): React.ReactElement {
  const { t } = useTranslation();
  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('home.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        {t('home.noSessions')}
      </AccessibleText>
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
});
