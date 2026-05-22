import { fetchJson } from './api';

/**
 * Right-to-erasure service — GDPR Art. 17 / Egypt PDPL.
 *
 * Coach-/admin-initiated erasure on behalf of a data subject. The backend
 * (`/erasure`, coach-or-higher) opens an append-only ticket on submit, then
 * crypto-shreds the tenant DEK on execute. Execution is irreversible — the
 * UI gates it behind an explicit confirmation.
 *
 * Wire shapes match the backend `ErasureTicketOut` DTO (snake_case).
 */

type ErasureStatus = 'pending' | 'completed';

interface ErasureTicketWire {
  id: string;
  tenant_id: string;
  athlete_user_id: string;
  requested_by: string;
  reason: string;
  status: string;
  /** Enumerated reference counts captured at execution time (null until executed). */
  references: Record<string, number> | null;
  created_at: string;
  completed_at: string | null;
}

export interface ErasureTicket {
  id: string;
  tenantId: string;
  athleteUserId: string;
  requestedBy: string;
  reason: string;
  status: ErasureStatus;
  references: Record<string, number> | null;
  createdAt: string;
  completedAt: string | null;
}

function toTicket(wire: ErasureTicketWire): ErasureTicket {
  return {
    id: wire.id,
    tenantId: wire.tenant_id,
    athleteUserId: wire.athlete_user_id,
    requestedBy: wire.requested_by,
    reason: wire.reason,
    status: wire.status === 'completed' ? 'completed' : 'pending',
    references: wire.references,
    createdAt: wire.created_at,
    completedAt: wire.completed_at,
  };
}

export interface SubmitErasureInput {
  athleteUserId: string;
  reason: string;
}

export async function submitErasure(input: SubmitErasureInput): Promise<ErasureTicket> {
  const wire = await fetchJson<ErasureTicketWire>('/erasure', {
    method: 'POST',
    body: JSON.stringify({
      athlete_user_id: input.athleteUserId,
      reason: input.reason,
    }),
  });
  return toTicket(wire);
}

export async function executeErasure(ticketId: string): Promise<ErasureTicket> {
  const wire = await fetchJson<ErasureTicketWire>(
    `/erasure/${encodeURIComponent(ticketId)}/execute`,
    { method: 'POST' },
  );
  return toTicket(wire);
}

export async function getErasureTicket(ticketId: string): Promise<ErasureTicket> {
  const wire = await fetchJson<ErasureTicketWire>(`/erasure/${encodeURIComponent(ticketId)}`);
  return toTicket(wire);
}
