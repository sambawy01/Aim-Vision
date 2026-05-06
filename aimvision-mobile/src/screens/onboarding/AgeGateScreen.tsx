/**
 * Age gate. Branches by computed age:
 *   age >= 18         → adult signup (Welcome)
 *   13 <= age < 18    → ParentalConsent (mode: 'minor')
 *   age < 13          → ParentalConsent (mode: 'coppa') with extra warnings
 *
 * Authority: docs/compliance/parental-consent-flow.md §2.1.
 */
import React, { useMemo, useState } from 'react';
import { Platform, StyleSheet, TextInput, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import { emitAuditEvent } from '../../services/audit';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'AgeGate'>;

export function ageFromDob(dob: Date, today: Date = new Date()): number {
  let age = today.getFullYear() - dob.getFullYear();
  const m = today.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
    age -= 1;
  }
  return age;
}

function parseDob(input: string): Date | null {
  // Expect YYYY-MM-DD; minimal scaffold parser.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(input.trim());
  if (!m) return null;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

export function AgeGateScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  const [dobInput, setDobInput] = useState('');
  const [country, setCountry] = useState('');
  const [error, setError] = useState<string | null>(null);

  const parsed = useMemo(() => parseDob(dobInput), [dobInput]);
  const age = parsed ? ageFromDob(parsed) : null;

  const isUnder13 = age !== null && age < 13;
  const isMinor = age !== null && age >= 13 && age < 18;
  const isAdult = age !== null && age >= 18;
  const ready = parsed !== null && country.length >= 2;

  const handleContinue = (): void => {
    if (!parsed || age === null) {
      setError(t('ageGate.errorFuture'));
      return;
    }
    if (parsed.getTime() > Date.now()) {
      setError(t('ageGate.errorFuture'));
      return;
    }
    setError(null);
    const dobIso = parsed.toISOString().slice(0, 10);
    if (isAdult) {
      emitAuditEvent({ eventType: 'age_gate_branched', payload: { branch: 'adult' } });
      navigation.navigate('Welcome');
      return;
    }
    if (isUnder13) {
      emitAuditEvent({ eventType: 'age_gate_branched', payload: { branch: 'coppa' } });
      navigation.navigate('ParentalConsent', { dob: dobIso, ageYears: age, mode: 'coppa' });
      return;
    }
    if (isMinor) {
      emitAuditEvent({ eventType: 'age_gate_branched', payload: { branch: 'minor' } });
      navigation.navigate('ParentalConsent', { dob: dobIso, ageYears: age, mode: 'minor' });
    }
  };

  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('ageGate.title')}</AccessibleText>
      <AccessibleText variant="bodySmall" color="textSecondary" style={styles.subtitle}>
        {t('ageGate.subtitle')}
      </AccessibleText>

      <View style={styles.field}>
        <AccessibleText variant="caption" color="textSecondary">
          {t('ageGate.dobLabel')}
        </AccessibleText>
        <TextInput
          value={dobInput}
          onChangeText={setDobInput}
          placeholder="YYYY-MM-DD"
          placeholderTextColor={colors.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType={Platform.select({ ios: 'numbers-and-punctuation', android: 'default' })}
          accessibilityLabel={t('ageGate.dobLabel')}
          testID="age-gate-dob"
          style={styles.input}
        />
      </View>

      <View style={styles.field}>
        <AccessibleText variant="caption" color="textSecondary">
          {t('ageGate.countryLabel')}
        </AccessibleText>
        <TextInput
          value={country}
          onChangeText={setCountry}
          placeholder="EG"
          placeholderTextColor={colors.textMuted}
          autoCapitalize="characters"
          accessibilityLabel={t('ageGate.countryLabel')}
          testID="age-gate-country"
          style={styles.input}
        />
      </View>

      {error ? (
        <AccessibleText color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      ) : null}

      {isMinor ? (
        <View style={styles.notice} testID="age-gate-minor-notice">
          <AccessibleText variant="title" color="warning">
            {t('ageGate.parentRequired')}
          </AccessibleText>
          <AccessibleText variant="bodySmall" color="textSecondary">
            {t('ageGate.parentRequiredDescription')}
          </AccessibleText>
        </View>
      ) : null}

      {isUnder13 ? (
        <View style={styles.notice} testID="age-gate-coppa-notice">
          <AccessibleText variant="title" color="danger">
            {t('ageGate.parentRequired')}
          </AccessibleText>
          <AccessibleText variant="bodySmall" color="textSecondary">
            {t('ageGate.coppaWarning')}
          </AccessibleText>
        </View>
      ) : null}

      <View style={styles.actions}>
        <RangeButton
          label={isAdult ? t('ageGate.proceedAdult') : t('ageGate.continue')}
          onPress={handleContinue}
          disabled={!ready}
          accessibilityLabel={t('ageGate.continue')}
        />
      </View>

      <AccessibleTouchable
        accessibilityLabel={t('common.back')}
        onPress={() => navigation.canGoBack() && navigation.goBack()}
        style={styles.back}
      >
        <AccessibleText color="textMuted">{t('common.back')}</AccessibleText>
      </AccessibleTouchable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.lg,
  },
  subtitle: {
    marginTop: spacing.sm,
    marginBottom: spacing.lg,
  },
  field: {
    marginBottom: spacing.md,
  },
  input: {
    marginTop: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.textPrimary,
    fontSize: 17,
    minHeight: 44,
  },
  error: {
    marginTop: spacing.sm,
  },
  notice: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  actions: {
    marginTop: spacing.xl,
  },
  back: {
    marginTop: spacing.lg,
    alignSelf: 'flex-start',
  },
});
