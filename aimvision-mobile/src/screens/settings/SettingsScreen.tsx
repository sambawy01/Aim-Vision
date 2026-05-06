import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { useRangeMode } from '../../components/RangeMode';
import { colors, spacing } from '../../theme/tokens';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'Settings'>;

export function SettingsScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  const { inRangeMode, setManualOverride } = useRangeMode();

  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('settings.title')}</AccessibleText>

      <AccessibleTouchable
        accessibilityLabel={t('settings.dataPrivacy')}
        onPress={() => navigation.navigate('DataPrivacy')}
        style={styles.row}
      >
        <AccessibleText variant="body">{t('settings.dataPrivacy')}</AccessibleText>
      </AccessibleTouchable>

      <AccessibleTouchable
        accessibilityLabel={t('settings.rangeMode')}
        onPress={() => setManualOverride(inRangeMode ? null : true)}
        style={styles.row}
      >
        <AccessibleText variant="body">{t('settings.rangeMode')}</AccessibleText>
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
});
