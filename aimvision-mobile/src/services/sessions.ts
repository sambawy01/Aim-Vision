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
  recording_count: number;
  shot_count: number;
  calibration_count: number;
  alignment_complete: boolean;
  calibration_complete: boolean;
  ended_at: string | null;
  partial_session: boolean;
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
  return api<Session>(`/sessions/${sessionId}/end`, { method: 'PATCH' });
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

export interface Recording {
  id: string;
  session_id: string;
  storage_uri: string;
  sha256: string | null;
  duration_ms: number | null;
  upload_state: string;
  source_kind: 'hero13' | 'phone_dev' | 'mock';
  session_clock_offset_ns: number | null;
  session_clock_offset_confidence: number | null;
}

/**
 * Multipart upload to POST /sessions/{id}/recording.
 *
 * Uses `expo-file-system/legacy`'s `uploadAsync` because RN 0.85's
 * stricter FormData polyfill rejects the legacy `{uri,name,type}`
 * shape (`"Unsupported FormDataPart implementation"`). `uploadAsync`
 * streams the file from disk natively, no JS-side Blob materialization.
 */
import {
  FileSystemUploadType,
  uploadAsync,
} from 'expo-file-system/legacy';
import { env as _envForUpload } from '../config/env';
import { useAuthStore as _authStoreForUpload } from '../state/authStore';

export async function uploadRecording(
  sessionId: string,
  opts: {
    fileUri: string;
    sourceKind?: 'hero13' | 'phone_dev' | 'mock';
    durationMs?: number;
    cameraClockOffsetMs?: number;
  },
): Promise<Recording> {
  const token = _authStoreForUpload.getState().accessToken;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const params: Record<string, string> = {
    source_kind: opts.sourceKind ?? 'phone_dev',
  };
  if (opts.durationMs !== undefined) params.duration_ms = String(opts.durationMs);
  if (opts.cameraClockOffsetMs !== undefined) {
    params.camera_clock_offset_ms = String(opts.cameraClockOffsetMs);
  }

  const res = await uploadAsync(
    `${_envForUpload.apiBaseUrl}/sessions/${sessionId}/recording`,
    opts.fileUri,
    {
      httpMethod: 'POST',
      uploadType: FileSystemUploadType.MULTIPART,
      fieldName: 'file',
      mimeType: 'video/mp4',
      parameters: params,
      headers,
    },
  );
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`HTTP ${res.status}: ${res.body || 'upload failed'}`);
  }
  return JSON.parse(res.body) as Recording;
}

export async function listRecordings(
  sessionId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<Recording[]> {
  return api<Recording[]>(`/sessions/${sessionId}/recording`, { signal: opts.signal });
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
