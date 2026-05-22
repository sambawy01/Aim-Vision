/**
 * Sign-in screen. Coaches/admins authenticate here (the onboarding flow at
 * AgeGate is for new athletes). On success `login()` stores the access token +
 * principal, and RootNavigator swaps to the App stack reactively.
 */
import React, { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import { login } from '../../services/auth';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'Login'>;

export function LoginScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const ready = email.trim().length > 0 && password.length > 0;

  const onSubmit = async (): Promise<void> => {
    setError(null);
    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      // No navigation needed: RootNavigator swaps to the App stack once the
      // principal lands in the store.
    } catch {
      setError(t('login.error'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('login.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.subtitle}>
        {t('login.subtitle')}
      </AccessibleText>

      <AccessibleText variant="bodySmall" color="textSecondary" style={styles.label}>
        {t('login.email')}
      </AccessibleText>
      <TextInput
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        style={styles.input}
        accessibilityLabel={t('login.email')}
        testID="login-email"
      />

      <AccessibleText variant="bodySmall" color="textSecondary" style={styles.label}>
        {t('login.password')}
      </AccessibleText>
      <TextInput
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        style={styles.input}
        accessibilityLabel={t('login.password')}
        testID="login-password"
      />

      {error ? (
        <AccessibleText
          variant="bodySmall"
          color="danger"
          style={styles.error}
          testID="login-error"
        >
          {error}
        </AccessibleText>
      ) : null}

      <View style={styles.actions}>
        <RangeButton
          label={t('login.submit')}
          onPress={() => void onSubmit()}
          disabled={!ready || submitting}
          accessibilityLabel={t('login.submit')}
        />
      </View>

      <AccessibleTouchable
        onPress={() => navigation.navigate('AgeGate')}
        accessibilityLabel={t('login.createAccount')}
        style={styles.linkRow}
      >
        <AccessibleText variant="bodySmall" color="accent">
          {t('login.createAccount')}
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
    gap: spacing.sm,
  },
  subtitle: {
    marginBottom: spacing.md,
  },
  label: {
    marginTop: spacing.sm,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    minHeight: 44,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  error: {
    marginTop: spacing.sm,
  },
  actions: {
    marginTop: spacing.lg,
  },
  linkRow: {
    marginTop: spacing.lg,
    alignItems: 'center',
  },
});
