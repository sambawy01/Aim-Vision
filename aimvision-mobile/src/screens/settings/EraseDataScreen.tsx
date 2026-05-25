/**
 * Right-to-erasure request flow (ADR-0011 / GDPR Art. 17).
 *
 * Two-step:
 *   1. Submit a ticket (POST /erasure {athlete_user_id, reason}).
 *   2. Confirm + execute the crypto-shred (POST /erasure/{id}/execute).
 *
 * Step 1 is reversible (a pending ticket can be ignored); step 2 is
 * destructive. We surface both states so the user always sees what
 * happened — there's no silent shred.
 */
import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { AccessibleTouchable } from '../../components/a11y/AccessibleTouchable';
import { useRangeMode } from '../../components/RangeMode';
import type { Theme } from '../../theme/tokens';
import { useAuthStore } from '../../state/authStore';
import {
  executeErasureTicket,
  submitErasureRequest,
  type ErasureTicket,
} from '../../services/erasure';

type Step =
  | { kind: 'form' }
  | { kind: 'pending'; ticket: ErasureTicket }
  | { kind: 'executing'; ticket: ErasureTicket }
  | { kind: 'completed'; ticket: ErasureTicket }
  | { kind: 'failed'; message: string };

export function EraseDataScreen(): React.ReactElement {
  const { theme } = useRangeMode();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const session = useAuthStore((s) => s.session);

  // The "default" athlete is the signed-in user — that's the legally
  // common case (your own right of erasure). A coach erasing one of
  // their athletes overrides the field manually.
  const [athleteId, setAthleteId] = useState(session?.athleteIdHash ?? '');
  const [reason, setReason] = useState('User-requested deletion');
  const [step, setStep] = useState<Step>({ kind: 'form' });

  const submit = async (): Promise<void> => {
    if (!athleteId.trim() || !reason.trim()) {
      setStep({ kind: 'failed', message: 'Athlete id and reason are both required.' });
      return;
    }
    try {
      const ticket = await submitErasureRequest({
        athlete_user_id: athleteId.trim(),
        reason: reason.trim(),
      });
      setStep({ kind: 'pending', ticket });
    } catch (e) {
      setStep({
        kind: 'failed',
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const execute = (ticket: ErasureTicket): void => {
    Alert.alert(
      'Execute erasure?',
      'This crypto-shreds the per-tenant encryption key. Recordings, shots, and ML data for this athlete become unreadable. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Erase data',
          style: 'destructive',
          onPress: async () => {
            setStep({ kind: 'executing', ticket });
            try {
              const completed = await executeErasureTicket(ticket.id);
              setStep({ kind: 'completed', ticket: completed });
            } catch (e) {
              setStep({
                kind: 'failed',
                message: e instanceof Error ? e.message : String(e),
              });
            }
          },
        },
      ],
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <AccessibleText variant="display">Erase data</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        File a right-to-erasure request (GDPR Art. 17 / ADR-0011). Pending
        requests can be reviewed before execution; execution is irreversible.
      </AccessibleText>

      {step.kind === 'form' || step.kind === 'failed' ? (
        <>
          <View style={styles.field}>
            <AccessibleText variant="caption" color="textSecondary">
              Athlete id (yourself by default)
            </AccessibleText>
            <TextInput
              style={styles.input}
              value={athleteId}
              onChangeText={setAthleteId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="user UUID"
              placeholderTextColor={theme.colors.textMuted}
            />
          </View>
          <View style={styles.field}>
            <AccessibleText variant="caption" color="textSecondary">
              Reason
            </AccessibleText>
            <TextInput
              style={[styles.input, styles.inputMultiline]}
              value={reason}
              onChangeText={setReason}
              multiline
              numberOfLines={3}
              placeholder="Why you want this data erased"
              placeholderTextColor={theme.colors.textMuted}
            />
          </View>
          {step.kind === 'failed' ? (
            <AccessibleText variant="body" color="danger" style={styles.body}>
              {step.message}
            </AccessibleText>
          ) : null}
          <AccessibleTouchable
            accessibilityLabel="Submit erasure request"
            onPress={submit}
            style={styles.primaryBtn}
          >
            <AccessibleText variant="body" color="white">
              Submit request
            </AccessibleText>
          </AccessibleTouchable>
        </>
      ) : null}

      {step.kind === 'pending' || step.kind === 'executing' || step.kind === 'completed' ? (
        <View style={styles.ticket}>
          <AccessibleText variant="title">Ticket</AccessibleText>
          <AccessibleText variant="caption" color="textMuted">
            {step.ticket.id}
          </AccessibleText>
          <AccessibleText variant="body" color="textSecondary" style={styles.body}>
            athlete: {step.ticket.athlete_user_id}
          </AccessibleText>
          <AccessibleText variant="body" color="textSecondary">
            reason: {step.ticket.reason}
          </AccessibleText>
          <AccessibleText
            variant="title"
            color={
              step.ticket.status === 'completed'
                ? 'success'
                : step.ticket.status === 'failed'
                  ? 'danger'
                  : 'warning'
            }
            style={styles.body}
          >
            status: {step.ticket.status}
          </AccessibleText>

          {step.kind === 'pending' ? (
            <AccessibleTouchable
              accessibilityLabel="Execute erasure (irreversible)"
              onPress={() => execute(step.ticket)}
              style={[styles.primaryBtn, styles.dangerBtn]}
            >
              <AccessibleText variant="body" color="white">
                Execute erasure (irreversible)
              </AccessibleText>
            </AccessibleTouchable>
          ) : null}
          {step.kind === 'executing' ? (
            <AccessibleText variant="body" color="textSecondary">
              Crypto-shredding the per-tenant DEK…
            </AccessibleText>
          ) : null}
          {step.kind === 'completed' ? (
            <AccessibleText variant="body" color="success">
              Done. The tenant's encryption key is shredded; downstream
              data is unreadable.
            </AccessibleText>
          ) : null}
        </View>
      ) : null}
    </ScrollView>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.bg },
    content: { padding: theme.spacing.lg, paddingBottom: theme.spacing.xxl, gap: theme.spacing.md },
    body: { marginVertical: theme.spacing.xs },
    field: { gap: theme.spacing.xs },
    input: {
      backgroundColor: theme.colors.surface,
      color: theme.colors.textPrimary,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      fontSize: 16,
      minHeight: 48,
    },
    inputMultiline: { minHeight: 80, textAlignVertical: 'top' },
    primaryBtn: {
      backgroundColor: theme.colors.accent,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      borderRadius: theme.radii.md,
      alignItems: 'center',
      marginTop: theme.spacing.md,
    },
    dangerBtn: { backgroundColor: theme.colors.danger },
    ticket: {
      backgroundColor: theme.colors.surface,
      borderRadius: theme.radii.md,
      padding: theme.spacing.md,
      gap: theme.spacing.xs,
    },
  });
}
