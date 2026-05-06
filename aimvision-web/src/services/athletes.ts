import { fetchJson } from './api';

export interface Athlete {
  id: string;
  displayName: string;
  email: string | null;
  joinedAt: string;
}

export async function listAthletes(): Promise<Athlete[]> {
  return fetchJson<Athlete[]>('/v1/athletes');
}

export async function getAthlete(id: string): Promise<Athlete> {
  return fetchJson<Athlete>(`/v1/athletes/${encodeURIComponent(id)}`);
}
