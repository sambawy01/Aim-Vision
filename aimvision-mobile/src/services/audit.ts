/**
 * Client-side audit breadcrumbs that feed Sentry plus the server audit log.
 * See docs/compliance/parental-consent-flow.md §10 for required event types.
 */
import { Sentry } from '../config/sentry';

export type AuditEventType =
  | 'consent_grant'
  | 'consent_revoke'
  | 'consent_version_change'
  | 'assent_recorded'
  | 'parental_method_used'
  | 're_consent_prompt_shown'
  | 'auto_purge_due'
  | 'age_gate_branched';

export interface AuditEvent {
  eventType: AuditEventType;
  payload?: Record<string, unknown>;
}

export function emitAuditEvent(event: AuditEvent): void {
  Sentry.addBreadcrumb({
    category: 'audit',
    type: 'info',
    level: 'info',
    message: event.eventType,
    data: event.payload,
  });
  // Server audit-log POST is wired in Sprint 5 (per parental-consent-flow.md §11).
}
