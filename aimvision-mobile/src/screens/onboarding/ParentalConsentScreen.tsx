/**
 * Parental consent screen.
 * Authority: docs/compliance/parental-consent-flow.md §3 (verifiable methods).
 * Methods supported: paper-PDF (gold standard), credit-card (COPPA §312.5(b)(2)(ii)),
 * email-plus-ID, video call.
 */
import React, { useState } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import { submitParentalConsent, type ParentalConsentRequest } from '../../services/auth';
import { emitAuditEvent } from '../../services/audit';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'ParentalConsent'>;
type Route = RouteProp<AuthStackParamList, 'ParentalConsent'>;

type Method = ParentalConsentRequest['method'];

const METHODS: Method[] = ['paper_pdf', 'credit_card', 'email_plus_id', 'video_call'];

export function ParentalConsentScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { t } = useTranslation();

  const [parentEmail, setParentEmail] = useState('');
  const [method, setMethod] = useState<Method>(
    route.params.mode === 'coppa' ? 'paper_pdf' : 'email_plus_id',
  );
  const [pdfUri, setPdfUri] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const onSubmit = async (): Promise<void> => {
    setSubmitting(true);
    try {
      const res = await submitParentalConsent({
        parentEmail,
        method,
        evidence: { pdfUri: pdfUri ?? undefined },
      });
      emitAuditEvent({
        eventType: 'parental_method_used',
        payload: { method, mode: route.params.mode, status: res.status },
      });
      setSubmitted(true);
      if (res.status === 'approved') {
        navigation.navigate('ChildSetup', { parentConsentToken: res.consentToken });
      }
    } catch {
      // Real error UI lives in Sprint 4. For now the button just re-enables.
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <View style={styles.container}>
        <AccessibleText variant="display">{t('parentalConsent.submittedTitle')}</AccessibleText>
        <AccessibleText variant="body" color="textSecondary" style={styles.subtitle}>
          {t('parentalConsent.submittedBody')}
        </AccessibleText>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">{t('parentalConsent.title')}</AccessibleText>
      <AccessibleText variant="bodySmall" color="textSecondary" style={styles.subtitle}>
        {t('parentalConsent.subtitle')}
      </AccessibleText>

      <View style={styles.field}>
        <AccessibleText variant="caption" color="textSecondary">
          {/* Plain label intentionally inline; treated as static, not a code-comment-only string. */}
          {t('parentalConsent.title')}
        </AccessibleText>
        <TextInput
          value={parentEmail}
          onChangeText={setParentEmail}
          placeholder="parent@example.com"
          placeholderTextColor={colors.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          accessibilityLabel={t('parentalConsent.title')}
          testID="parent-email"
          style={styles.input}
        />
      </View>

      <View style={styles.methodList}>
        {METHODS.map((m) => {
          const selected = method === m;
          return (
            <AccessibleTouchable
              key={m}
              accessibilityLabel={t(`parentalConsent.method.${m}`)}
              onPress={() => setMethod(m)}
              testID={`method-${m}`}
              style={[
                styles.methodRow,
                {
                  borderColor: selected ? colors.accent : colors.border,
                  backgroundColor: selected ? colors.surfaceElevated : colors.surface,
                },
              ]}
            >
              <View style={styles.methodTextWrap}>
                <AccessibleText variant="body">{t(`parentalConsent.method.${m}`)}</AccessibleText>
              </View>
            </AccessibleTouchable>
          );
        })}
      </View>

      {method === 'paper_pdf' || method === 'email_plus_id' ? (
        <AccessibleTouchable
          accessibilityLabel={t('parentalConsent.uploadPdf')}
          onPress={() => setPdfUri('stub://pending-document-picker')}
          testID="upload-pdf"
          style={styles.uploadStub}
        >
          <AccessibleText color="accent">{t('parentalConsent.uploadPdf')}</AccessibleText>
        </AccessibleTouchable>
      ) : null}

      <View style={styles.actions}>
        <RangeButton
          label={t('parentalConsent.submit')}
          onPress={onSubmit}
          disabled={submitting || parentEmail.length < 3}
          accessibilityLabel={t('parentalConsent.submit')}
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
  methodList: {
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  methodRow: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: 'flex-start',
    minHeight: 56,
  },
  methodTextWrap: {
    flex: 1,
  },
  uploadStub: {
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  actions: {
    marginTop: spacing.xl,
  },
});
