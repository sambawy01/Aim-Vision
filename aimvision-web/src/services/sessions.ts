import { fetchJson } from './api';

/** Wire shape matches the backend's SessionOut DTO (snake_case). */
interface SessionWire {
  id: string;
  org_id: string;
  athlete_user_id: string;
  discipline: string;
  started_at: string;
  ended_at: string | null;
  partial_session: boolean;
}

/** Wire shape matches the backend's SessionSummaryOut DTO. */
interface SessionSummaryWire {
  session_id: string;
  recording_count: number;
  shot_count: number;
  calibration_count: number;
  alignment_complete: boolean;
  calibration_complete: boolean;
  ended_at: string | null;
  partial_session: boolean;
}

export interface Session {
  id: string;
  orgId: string;
  athleteId: string;
  discipline: string;
  startedAt: string;
  endedAt: string | null;
  partialSession: boolean;
}

export interface SessionSummary {
  sessionId: string;
  recordingCount: number;
  shotCount: number;
  calibrationCount: number;
  alignmentComplete: boolean;
  calibrationComplete: boolean;
  endedAt: string | null;
  partialSession: boolean;
}

function toSession(wire: SessionWire): Session {
  return {
    id: wire.id,
    orgId: wire.org_id,
    athleteId: wire.athlete_user_id,
    discipline: wire.discipline,
    startedAt: wire.started_at,
    endedAt: wire.ended_at,
    partialSession: wire.partial_session,
  };
}

function toSummary(wire: SessionSummaryWire): SessionSummary {
  return {
    sessionId: wire.session_id,
    recordingCount: wire.recording_count,
    shotCount: wire.shot_count,
    calibrationCount: wire.calibration_count,
    alignmentComplete: wire.alignment_complete,
    calibrationComplete: wire.calibration_complete,
    endedAt: wire.ended_at,
    partialSession: wire.partial_session,
  };
}

export async function listSessions(): Promise<Session[]> {
  const wire = await fetchJson<SessionWire[]>('/sessions');
  return wire.map(toSession);
}

export async function getSession(id: string): Promise<Session> {
  const wire = await fetchJson<SessionWire>(`/sessions/${encodeURIComponent(id)}`);
  return toSession(wire);
}

export async function getSessionSummary(id: string): Promise<SessionSummary> {
  const wire = await fetchJson<SessionSummaryWire>(`/sessions/${encodeURIComponent(id)}/summary`);
  return toSummary(wire);
}

export interface CreateSessionInput {
  athleteUserId: string;
  orgId: string;
  discipline?: string;
  startedAt?: string;
}

export async function createSession(input: CreateSessionInput): Promise<Session> {
  const body: Record<string, unknown> = {
    athlete_user_id: input.athleteUserId,
    org_id: input.orgId,
  };
  if (input.discipline) body.discipline = input.discipline;
  if (input.startedAt) body.started_at = input.startedAt;
  const wire = await fetchJson<SessionWire>('/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return toSession(wire);
}

/** Wire shape matches the backend's ProcessSessionOut DTO. */
interface ProcessSessionWire {
  session_id: string;
  workflow_id: string;
  task_queue: string;
}

export interface ProcessSessionResult {
  sessionId: string;
  workflowId: string;
  taskQueue: string;
}

export async function processSession(
  id: string,
  partialSession = false,
): Promise<ProcessSessionResult> {
  const wire = await fetchJson<ProcessSessionWire>(`/sessions/${encodeURIComponent(id)}/process`, {
    method: 'POST',
    body: JSON.stringify({ partial_session: partialSession }),
  });
  return {
    sessionId: wire.session_id,
    workflowId: wire.workflow_id,
    taskQueue: wire.task_queue,
  };
}

/** Subset of the coaching-note structure the UI renders. The backend
 * returns the full structured note (coaching-notes schema v1) under
 * `note`; we type the fields we display. */
export interface CoachingDiagnostic {
  category: string;
  confidence: number;
  coaching_action: string;
  evidence_shot_ids: string[];
}

export interface CoachingNoteBody {
  headline: string;
  top_diagnostics: CoachingDiagnostic[];
  recommended_drills: string[];
  tone_mode: string;
  language: string;
  degraded: boolean;
  verifier_passed: boolean;
  confidence_overall: number;
}

interface CoachingNoteWire {
  id: string;
  session_id: string;
  headline: string;
  verifier_passed: boolean;
  degraded: boolean;
  model_version: string;
  generated_at: string;
  note: CoachingNoteBody;
}

export interface CoachingNote {
  id: string;
  sessionId: string;
  headline: string;
  verifierPassed: boolean;
  degraded: boolean;
  modelVersion: string;
  generatedAt: string;
  note: CoachingNoteBody;
}

export async function getCoachingNote(id: string): Promise<CoachingNote> {
  const wire = await fetchJson<CoachingNoteWire>(
    `/sessions/${encodeURIComponent(id)}/coaching-note`,
  );
  return {
    id: wire.id,
    sessionId: wire.session_id,
    headline: wire.headline,
    verifierPassed: wire.verifier_passed,
    degraded: wire.degraded,
    modelVersion: wire.model_version,
    generatedAt: wire.generated_at,
    note: wire.note,
  };
}
