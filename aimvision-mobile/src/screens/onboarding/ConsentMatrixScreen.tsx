/**
 * Consent matrix screen. Authority: docs/compliance/parental-consent-flow.md §4.3 + §9.3.
 * Per-category × per-purpose grid; submit calls services/consent.ts::grant; defaults off.
 */
import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { ConsentMatrix } from '../../components/ConsentMatrix';
import { colors, spacing } from '../../theme/tokens';
import { useConsentStore } from '../../state/consentStore';
import { grant } from '../../services/consent';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'ConsentMatrix'>;
type Route = RouteProp<AuthStackParamList, 'ConsentMatrix'>;

export function ConsentMatrixScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { t } = useTranslation();
  const matrix = useConsentStore((s) => s.matrix);
  const version = useConsentStore((s) => s.version);
  const [saving, setSaving] = useState(false);

  const onSave = async (): Promise<void> => {
    setSaving(true);
    try {
      await grant(matrix, version, route.params?.childAccountId);
      // End of the child onboarding flow — wipe the stack so the user can't
      // back-navigate to revoke a consent they just submitted.
      navigation.reset({ index: 0, routes: [{ name: 'Welcome' }] });
    } catch {
      // Sprint 4 surfaces a toast/alert.
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">{t('consent.title')}</AccessibleText>
      <AccessibleText variant="bodySmall" color="textSecondary" style={styles.subtitle}>
        {t('consent.subtitle')}
      </AccessibleText>

      <ConsentMatrix />

      <View style={styles.actions}>
        <RangeButton
          label={t('consent.save')}
          onPress={onSave}
          disabled={saving}
          accessibilityLabel={t('consent.save')}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  subtitle: {
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  actions: {
    marginTop: spacing.xl,
  },
});
