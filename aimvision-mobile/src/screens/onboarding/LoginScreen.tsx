/**
 * Local-dev / staging login screen.
 *
 * Calls `services/auth.ts::login()` which maps the backend `LoginOut`
 * (PR #88) to the camelCase AuthSession shape. On success, the auth
 * store updates → `RootNavigator` reactively swaps `AuthStack` → `AppStack`.
 *
 * This screen is a Phase-1 placeholder before the GoTrue cutover
 * (ADR-0010) — once the web/mobile clients switch to `/auth/exchange`,
 * this calls GoTrue's REST API instead of the stub `/auth/login`.
 */
import React, { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import { login } from '../../services/auth';

export function LoginScreen(): React.ReactElement {
  const [email, setEmail] = useState('coach@example.com');
  const [password, setPassword] = useState('demopassword123');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSignIn = async (): Promise<void> => {
    if (!email.trim() || !password) {
      setError('Email and password are required');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
      // Success: RootNavigator swaps AuthStack → AppStack via the auth
      // store subscription. No imperative navigation needed.
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg.includes('401') ? 'Invalid email or password' : msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">Sign in</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.subtitle}>
        Use your AIMVISION account to continue.
      </AccessibleText>

      <View style={styles.field}>
        <AccessibleText variant="caption" color="textSecondary">
          Email
        </AccessibleText>
        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          textContentType="emailAddress"
          autoComplete="email"
          editable={!submitting}
          accessibilityLabel="Email"
          placeholder="you@example.com"
          placeholderTextColor={colors.textSecondary}
        />
      </View>

      <View style={styles.field}>
        <AccessibleText variant="caption" color="textSecondary">
          Password
        </AccessibleText>
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          textContentType="password"
          autoComplete="current-password"
          editable={!submitting}
          accessibilityLabel="Password"
          placeholder="••••••••"
          placeholderTextColor={colors.textSecondary}
        />
      </View>

      {error && (
        <AccessibleText variant="body" color="danger" style={styles.error}>
          {error}
        </AccessibleText>
      )}

      <View style={styles.actions}>
        {submitting ? (
          <ActivityIndicator color={colors.textPrimary} accessibilityLabel="Signing in" />
        ) : (
          <RangeButton
            label="Sign in"
            onPress={onSignIn}
            disabled={submitting}
            accessibilityLabel="Sign in"
          />
        )}
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
    marginBottom: spacing.lg,
  },
  field: {
    marginBottom: spacing.md,
  },
  input: {
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    color: colors.textPrimary,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 16,
    minHeight: 48,
  },
  error: {
    marginTop: spacing.sm,
  },
  actions: {
    marginTop: spacing.xl,
  },
});
