import { fetchJson } from './api';

/** Wire shape matches the backend's AthleteOut DTO (snake_case). */
interface AthleteWire {
  id: string;
  display_name: string;
  email: string | null;
  joined_at: string;
}

export interface Athlete {
  id: string;
  displayName: string;
  email: string | null;
  joinedAt: string;
}

function toAthlete(wire: AthleteWire): Athlete {
  return {
    id: wire.id,
    displayName: wire.display_name,
    email: wire.email,
    joinedAt: wire.joined_at,
  };
}

export async function listAthletes(): Promise<Athlete[]> {
  const wire = await fetchJson<AthleteWire[]>('/athletes');
  return wire.map(toAthlete);
}

export async function getAthlete(id: string): Promise<Athlete> {
  const wire = await fetchJson<AthleteWire>(`/athletes/${encodeURIComponent(id)}`);
  return toAthlete(wire);
}
