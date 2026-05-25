/**
 * Drills + athletes — the two pickers the New Session flow needs.
 * Backend: GET /drills, GET /athletes.
 */
import { api } from './api';

export interface Drill {
  id: string;
  name: string;
  description: string;
  discipline: string;
  target_categories: string[];
}

export interface Athlete {
  id: string;
  display_name: string;
  email: string | null;
  joined_at: string;
}

export async function listDrills(opts: { signal?: AbortSignal } = {}): Promise<Drill[]> {
  return api<Drill[]>('/drills', { signal: opts.signal });
}

export async function listAthletes(opts: { signal?: AbortSignal } = {}): Promise<Athlete[]> {
  return api<Athlete[]>('/athletes', { signal: opts.signal });
}

export async function getAthlete(
  athleteId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<Athlete> {
  return api<Athlete>(`/athletes/${athleteId}`, { signal: opts.signal });
}

export interface AthleteProgress {
  athlete_id: string;
  sessions_analyzed: number;
  sessions: Array<{
    session_id: string;
    started_at: string;
    shot_count: number;
    diagnostic_chips: string[];
  }>;
  deltas: Record<string, number>;
}

export async function getAthleteProgress(
  athleteId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<AthleteProgress> {
  return api<AthleteProgress>(`/athletes/${athleteId}/progress`, { signal: opts.signal });
}
