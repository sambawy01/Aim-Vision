/**
 * Supervised child setup. Authority: docs/compliance/parental-consent-flow.md §9.2.
 * Age-appropriate copy, no marketing nudges, parent-set defaults are visible.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import { emitAuditEvent } from '../../services/audit';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'ChildSetup'>;

export function ChildSetupScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();

  const onAssent = (): void => {
    emitAuditEvent({ eventType: 'assent_recorded' });
    navigation.navigate('ConsentMatrix', {});
  };

  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('childSetup.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        {t('childSetup.body')}
      </AccessibleText>
      <View style={styles.actions}>
        <RangeButton
          label={t('childSetup.confirmAssent')}
          onPress={onAssent}
          accessibilityLabel={t('childSetup.confirmAssent')}
        />
      </View>
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
  actions: {
    marginTop: spacing.xl,
  },
});
