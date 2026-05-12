import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import type { AppStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList, 'Settings'>;

export function SettingsScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  const { inRangeMode, setManualOverride, theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const rangeModeLabel = `${t('settings.rangeMode')} · ${
    inRangeMode ? t('common.on') : t('common.off')
  }`;

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
  });
}
