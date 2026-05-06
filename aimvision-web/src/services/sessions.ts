import { fetchJson } from './api';

export interface Session {
  id: string;
  athleteId: string;
  startedAt: string;
  endedAt: string | null;
  shotCount: number;
}

export async function listSessions(): Promise<Session[]> {
  return fetchJson<Session[]>('/v1/sessions');
}

export async function getSession(id: string): Promise<Session> {
  return fetchJson<Session>(`/v1/sessions/${encodeURIComponent(id)}`);
}
