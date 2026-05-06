/**
 * Consent grant / revoke wire-up.
 * See docs/compliance/parental-consent-flow.md §10 for required audit fields.
 */
import { api } from './api';
import {
  type ConsentCategory,
  type ConsentMatrix,
  type ConsentPurpose,
  CONSENT_CATEGORIES,
  CONSENT_PURPOSES,
} from '../state/consentStore';
import { emitAuditEvent } from './audit';

export interface ConsentGrant {
  category: ConsentCategory;
  purpose: ConsentPurpose;
  granted: boolean;
}

export interface ConsentSubmission {
  childAccountId?: string;
  version: string;
  grants: ConsentGrant[];
}

function flatten(matrix: ConsentMatrix): ConsentGrant[] {
  const out: ConsentGrant[] = [];
  for (const cat of CONSENT_CATEGORIES) {
    for (const pur of CONSENT_PURPOSES) {
      out.push({ category: cat, purpose: pur, granted: matrix[cat][pur] });
    }
  }
  return out;
}

export async function grant(
  matrix: ConsentMatrix,
  version: string,
  childAccountId?: string,
): Promise<void> {
  const submission: ConsentSubmission = {
    childAccountId,
    version,
    grants: flatten(matrix),
  };
  await api<void>('/consent/grant', { method: 'POST', body: submission });
  emitAuditEvent({
    eventType: 'consent_grant',
    payload: { version, childAccountId, count: submission.grants.length },
  });
}

export async function revoke(
  category: ConsentCategory,
  purpose: ConsentPurpose,
  childAccountId?: string,
): Promise<void> {
  await api<void>('/consent/revoke', {
    method: 'POST',
    body: { category, purpose, childAccountId },
  });
  emitAuditEvent({
    eventType: 'consent_revoke',
    payload: { category, purpose, childAccountId },
  });
}
