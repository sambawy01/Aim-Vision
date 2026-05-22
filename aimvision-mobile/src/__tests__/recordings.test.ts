/**
 * Recording upload service — ADR-0009 capture→ingest seam.
 * Mocks global fetch + the auth store; no native module needed.
 */
import { uploadRecording } from '../services/recordings';
import { ApiError } from '../services/api';
import { useAuthStore } from '../state/authStore';

jest.mock('../config/env', () => ({ env: { apiBaseUrl: 'http://test.local' } }));

describe('uploadRecording', () => {
  const fetchMock = jest.fn();

  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
    fetchMock.mockReset();
    useAuthStore.setState({ accessToken: 'tok-123' });
  });

  it('POSTs multipart to /sessions/{id}/recording with the bearer token', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      text: async () =>
        JSON.stringify({ id: 'rec-1', session_id: 'sess-1', upload_state: 'uploaded' }),
    });

    const out = await uploadRecording('sess-1', { fileUri: 'file:///tmp/clip.mp4' });

    expect(out).toEqual({ id: 'rec-1', sessionId: 'sess-1', uploadState: 'uploaded' });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe('http://test.local/sessions/sess-1/recording');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer tok-123');
    // Content-Type must be left unset so the runtime adds the multipart boundary.
    expect(init.headers['Content-Type']).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('throws ApiError on a non-2xx response', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => '{"detail":"unauthorized"}',
    });
    await expect(uploadRecording('sess-1', { fileUri: 'file:///x.mp4' })).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
