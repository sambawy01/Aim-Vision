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
