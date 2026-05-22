/**
 * Recording upload — pushes a finalized local MP4 to the backend so the
 * post-session ML pipeline can run over it. Closes the ADR-0009 capture→ingest
 * seam: `CapturePhoneScreen` records to a local file, this uploads it to
 * `POST /sessions/{id}/recording` tagged `phone_dev`.
 *
 * The shared `api()` helper forces `Content-Type: application/json`, so the
 * multipart upload uses `fetch` directly and lets the runtime set the
 * multipart boundary. The bearer token comes from the same auth store.
 */
import { env } from '../config/env';
import { useAuthStore } from '../state/authStore';
import { ApiError } from './api';

export interface UploadRecordingParams {
  /** Local file URI from Vision Camera's `onRecordingFinished` (e.g. file://…). */
  fileUri: string;
  /** Camera backend tag. Phone capture is always `phone_dev` (ADR-0009). */
  sourceKind?: 'phone_dev' | 'hero13';
  durationMs?: number;
  cameraClockOffsetMs?: number;
}

export interface UploadedRecording {
  id: string;
  sessionId: string;
  uploadState: string;
}

/** Wire shape of the backend's RecordingOut (snake_case subset we use). */
interface RecordingWire {
  id: string;
  session_id: string;
  upload_state: string;
}

export async function uploadRecording(
  sessionId: string,
  params: UploadRecordingParams,
): Promise<UploadedRecording> {
  const { fileUri, sourceKind = 'phone_dev', durationMs, cameraClockOffsetMs } = params;

  const form = new FormData();
  // React Native's FormData accepts a {uri,name,type} descriptor for files.
  form.append('file', {
    uri: fileUri,
    name: 'capture.mp4',
    type: 'video/mp4',
  } as unknown as Blob);
  form.append('source_kind', sourceKind);
  if (durationMs != null) form.append('duration_ms', String(durationMs));
  if (cameraClockOffsetMs != null) {
    form.append('camera_clock_offset_ms', String(cameraClockOffsetMs));
  }

  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  // Intentionally NOT setting Content-Type — the runtime adds the multipart
  // boundary. Setting it manually would break the upload.

  const res = await fetch(
    `${env.apiBaseUrl}/sessions/${encodeURIComponent(sessionId)}/recording`,
    { method: 'POST', headers, body: form },
  );

  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }

  if (!res.ok) {
    throw new ApiError(res.status, `recording upload failed (HTTP ${res.status})`, parsed);
  }

  const wire = parsed as RecordingWire;
  return { id: wire.id, sessionId: wire.session_id, uploadState: wire.upload_state };
}
