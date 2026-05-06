/**
 * Data & Privacy. Surfaces consent revoke and DSAR per
 * docs/compliance/parental-consent-flow.md §9.4 / §9.5.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { colors, spacing } from '../../theme/tokens';

export function DataPrivacyScreen(): React.ReactElement {
  const { t } = useTranslation();
  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('dataPrivacy.title')}</AccessibleText>

      <AccessibleTouchable
        accessibilityLabel={t('dataPrivacy.revoke')}
        onPress={() => undefined}
        style={styles.row}
      >
        <AccessibleText variant="body">{t('dataPrivacy.revoke')}</AccessibleText>
      </AccessibleTouchable>

      <AccessibleTouchable
        accessibilityLabel={t('dataPrivacy.dsar')}
        onPress={() => undefined}
        style={styles.row}
      >
        <AccessibleText variant="body">{t('dataPrivacy.dsar')}</AccessibleText>
      </AccessibleTouchable>

      <AccessibleTouchable
        accessibilityLabel={t('dataPrivacy.delete')}
        onPress={() => undefined}
        style={[styles.row, styles.dangerRow]}
      >
        <AccessibleText variant="body" color="danger">
          {t('dataPrivacy.delete')}
        </AccessibleText>
      </AccessibleTouchable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  row: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'flex-start',
    minHeight: 56,
  },
  dangerRow: {
    borderColor: colors.danger,
  },
});
