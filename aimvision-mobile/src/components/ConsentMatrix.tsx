/**
 * Consent matrix grid. Per docs/compliance/parental-consent-flow.md §4.3 and §9.3:
 * never bundled, each cell is independently grantable / revocable, defaults are off.
 */
import React from 'react';
import { StyleSheet, Switch, View } from 'react-native';
import { useTranslation } from '../hooks/useTranslation';
import {
  CONSENT_CATEGORIES,
  CONSENT_PURPOSES,
  type ConsentCategory,
  type ConsentPurpose,
  useConsentStore,
} from '../state/consentStore';
import { AccessibleText } from './a11y/AccessibleText';
import { colors, spacing } from '../theme/tokens';

export function ConsentMatrix(): React.ReactElement {
  const { t } = useTranslation();
  const matrix = useConsentStore((s) => s.matrix);
  const toggle = useConsentStore((s) => s.toggle);

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <View style={styles.categoryCell}>
          <AccessibleText variant="bodySmall" color="textSecondary">
            {t('consent.headerCategory')}
          </AccessibleText>
        </View>
        {CONSENT_PURPOSES.map((purpose) => (
          <View key={purpose} style={styles.purposeCell}>
            <AccessibleText variant="caption" color="textSecondary">
              {t(`consent.purpose.${purpose}`)}
            </AccessibleText>
          </View>
        ))}
      </View>

      {CONSENT_CATEGORIES.map((category) => (
        <View key={category} style={styles.row} testID={`consent-row-${category}`}>
          <View style={styles.categoryCell}>
            <AccessibleText variant="bodySmall">
              {t(`consent.category.${category}`)}
            </AccessibleText>
          </View>
          {CONSENT_PURPOSES.map((purpose) => (
            <CheckboxCell
              key={`${category}.${purpose}`}
              category={category}
              purpose={purpose}
              value={matrix[category][purpose]}
              onToggle={() => toggle(category, purpose)}
              label={t(`consent.cell`, {
                category: t(`consent.category.${category}`),
                purpose: t(`consent.purpose.${purpose}`),
              })}
            />
          ))}
        </View>
      ))}
    </View>
  );
}

interface CheckboxCellProps {
  category: ConsentCategory;
  purpose: ConsentPurpose;
  value: boolean;
  onToggle: () => void;
  label: string;
}

function CheckboxCell({
  category,
  purpose,
  value,
  onToggle,
  label,
}: CheckboxCellProps): React.ReactElement {
  return (
    <View style={styles.purposeCell}>
      <Switch
        value={value}
        onValueChange={onToggle}
        accessibilityLabel={label}
        accessibilityRole="switch"
        accessibilityState={{ checked: value }}
        testID={`consent-${category}-${purpose}`}
        thumbColor={value ? colors.accent : colors.textMuted}
        trackColor={{ false: colors.border, true: colors.accentPressed }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: spacing.md,
  },
  headerRow: {
    flexDirection: 'row',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  categoryCell: {
    flex: 1.4,
    paddingHorizontal: spacing.sm,
  },
  purposeCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xs,
  },
});
