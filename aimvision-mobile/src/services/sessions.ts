/**
 * Sessions API client.
 *
 * Backend contract: `aimvision-backend/app/schemas/session.py`. Field
 * names are snake_case on the wire; we mirror them in TS to avoid
 * mapping noise — the mobile player UI is the only consumer.
 */
import { api } from './api';

export interface Session {
  id: string;
  org_id: string;
  athlete_user_id: string;
  discipline: string;
  started_at: string;
  ended_at: string | null;
  partial_session: boolean;
}

export interface SessionCreateRequest {
  athlete_user_id: string;
  org_id: string;
  discipline: string;
  /** ISO timestamp; defaults to now() on the backend if omitted. */
  started_at?: string;
}

export interface SessionSummary {
  session_id: string;
  shot_count: number;
  duration_s: number | null;
  diagnostic_chips: string[];
}

export interface Shot {
  id: string;
  session_id: string;
  seq: number;
  t_ms: number;
  outcome: 'hit' | 'miss' | 'unknown';
  confidence: number | null;
}

export async function listSessions(opts: { signal?: AbortSignal } = {}): Promise<Session[]> {
  return api<Session[]>('/sessions', { signal: opts.signal });
}

export async function getSession(
  sessionId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<Session> {
  return api<Session>(`/sessions/${sessionId}`, { signal: opts.signal });
}

export async function createSession(req: SessionCreateRequest): Promise<Session> {
  return api<Session>('/sessions', { method: 'POST', body: req });
}

export async function endSession(sessionId: string): Promise<Session> {
  return api<Session>(`/sessions/${sessionId}/end`, { method: 'POST' });
}

export async function getSessionSummary(
  sessionId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<SessionSummary> {
  return api<SessionSummary>(`/sessions/${sessionId}/summary`, { signal: opts.signal });
}

export async function listSessionShots(
  sessionId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<Shot[]> {
  return api<Shot[]>(`/sessions/${sessionId}/shots`, { signal: opts.signal });
}

export interface CoachingNote {
  session_id: string;
  body: string;
  generated_at: string | null;
}

export async function getCoachingNote(
  sessionId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<CoachingNote | null> {
  try {
    return await api<CoachingNote>(`/sessions/${sessionId}/coaching-note`, { signal: opts.signal });
  } catch (e) {
    if (e instanceof Error && /404/.test(e.message)) return null;
    throw e;
  }
}
