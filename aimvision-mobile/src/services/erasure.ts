/**
 * Right-to-erasure (GDPR Art. 17 / ADR-0011) — mobile client.
 *
 * Two-step flow:
 *  1. `submitErasureRequest({athlete_user_id, reason})` — creates a
 *     pending ticket.
 *  2. `executeErasureTicket(ticketId)` — actually crypto-shreds the
 *     per-tenant DEK and marks the ticket complete. Separated so
 *     destructive action requires a confirmation step.
 */
import { api } from './api';

export interface ErasureTicket {
  id: string;
  tenant_id: string;
  athlete_user_id: string;
  requested_by: string;
  reason: string;
  status: 'pending' | 'completed' | 'failed' | string;
  references: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

export interface ErasureRequestIn {
  athlete_user_id: string;
  reason: string;
}

export async function submitErasureRequest(req: ErasureRequestIn): Promise<ErasureTicket> {
  return api<ErasureTicket>('/erasure', { method: 'POST', body: req });
}

export async function getErasureTicket(
  ticketId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<ErasureTicket> {
  return api<ErasureTicket>(`/erasure/${ticketId}`, { signal: opts.signal });
}

export async function executeErasureTicket(ticketId: string): Promise<ErasureTicket> {
  return api<ErasureTicket>(`/erasure/${ticketId}/execute`, { method: 'POST' });
}
