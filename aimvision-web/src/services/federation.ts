import { fetchJson } from './api';

/**
 * Federation tier dashboard service — Sprint 4 EPIC 4.5.
 *
 * Wire format expected from `/v1/federation/overview` and
 * `/v1/federation/clubs`. The backend endpoint is not yet implemented;
 * the routes consume this service through React Query so swapping the
 * stub to a real fetch is a one-line change.
 */

export interface FederationOverview {
  federationId: string;
  federationName: string;
  athletesTotal: number;
  clubsActive: number;
  sessionsLast30d: number;
  /** Avg sessions per athlete in the last 30 days. Headline activity
   * indicator surfaced on the dashboard card. */
  engagementRate: number;
  /** Talent cohorts under federation control. Each cohort is a named
   * group with an athlete count; the dashboard drills into a cohort to
   * see its athletes' performance trends. */
  talentCohorts: TalentCohort[];
}

export interface TalentCohort {
  id: string;
  name: string;
  athletesCount: number;
  /** Median sessions per athlete in this cohort, last 30d. Used to spot
   * cohorts that are under-training. */
  medianSessionsPer30d: number;
}

export interface ClubMembership {
  clubId: string;
  clubName: string;
  athletesCount: number;
  coachesCount: number;
  /** ISO 8601 timestamp of the most recent session captured in this club. */
  lastSessionAt: string | null;
  status: 'active' | 'paused' | 'pending_setup';
}

export async function getFederationOverview(): Promise<FederationOverview> {
  return fetchJson<FederationOverview>('/v1/federation/overview');
}

export async function listFederationClubs(): Promise<ClubMembership[]> {
  return fetchJson<ClubMembership[]>('/v1/federation/clubs');
}
