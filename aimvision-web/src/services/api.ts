import { env } from '@/config/env';
import { useAuthStore } from '@/state/authStore';
import { useTenancyStore } from '@/state/tenancyStore';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = 'ApiError';
  }
}

interface RefreshResponse {
  access_token: string;
}

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${env.apiBaseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // refresh token is httpOnly cookie
      });
      if (!res.ok) return null;
      const body = (await res.json()) as RefreshResponse;
      useAuthStore.getState().setAccessToken(body.access_token);
      return body.access_token;
    } catch {
      return null;
    } finally {
      // allow next refresh after a tick
      setTimeout(() => {
        refreshInFlight = null;
      }, 0);
    }
  })();

  return refreshInFlight;
}

interface FetchAuthInit extends RequestInit {
  /** Skip the 401 → refresh → retry loop (used internally to avoid recursion). */
  _skipRefresh?: boolean;
}

/**
 * Authenticated fetch wrapper.
 * - Prefixes API base URL when `input` is a relative path.
 * - Attaches `Authorization: Bearer <accessToken>` when present.
 * - Attaches `X-Tenant-Scope` from the tenancy store.
 * - On 401, calls `/auth/refresh` once and retries; otherwise clears auth.
 */
export async function fetchAuth(input: string, init: FetchAuthInit = {}): Promise<Response> {
  const url = input.startsWith('http') ? input : `${env.apiBaseUrl}${input}`;
  const headers = new Headers(init.headers);

  const token = useAuthStore.getState().accessToken;
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const tenant = useTenancyStore.getState().current?.tenantId;
  if (tenant && !headers.has('X-Tenant-Scope')) {
    headers.set('X-Tenant-Scope', tenant);
  }

  if (init.body && !headers.has('Content-Type') && typeof init.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(url, {
    ...init,
    headers,
    credentials: init.credentials ?? 'include',
  });

  if (res.status !== 401 || init._skipRefresh) {
    return res;
  }

  const newToken = await refreshAccessToken();
  if (!newToken) {
    useAuthStore.getState().clear();
    return res;
  }

  // retry once with the fresh token
  const retryHeaders = new Headers(init.headers);
  retryHeaders.set('Authorization', `Bearer ${newToken}`);
  if (tenant) retryHeaders.set('X-Tenant-Scope', tenant);
  if (init.body && !retryHeaders.has('Content-Type') && typeof init.body === 'string') {
    retryHeaders.set('Content-Type', 'application/json');
  }
  return fetch(url, {
    ...init,
    headers: retryHeaders,
    credentials: init.credentials ?? 'include',
    _skipRefresh: true,
  } as FetchAuthInit);
}

export async function fetchJson<T>(input: string, init?: FetchAuthInit): Promise<T> {
  const res = await fetchAuth(input, init);
  const body = (await res.json().catch(() => null)) as unknown;
  if (!res.ok) {
    throw new ApiError(res.status, `API ${res.status} for ${input}`, body);
  }
  return body as T;
}
