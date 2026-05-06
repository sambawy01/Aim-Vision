import { fetchJson } from './api';
import { useAuthStore, type Principal } from '@/state/authStore';
import { useTenancyStore, type TenantMembership } from '@/state/tenancyStore';

interface LoginResponse {
  access_token: string;
  principal: Principal;
  memberships: TenantMembership[];
}

export async function login(email: string, password: string): Promise<void> {
  const body = await fetchJson<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  useAuthStore.getState().setSession(body.access_token, body.principal);
  useTenancyStore.getState().setMemberships(body.memberships);
}

export async function logout(): Promise<void> {
  try {
    await fetchJson('/auth/logout', { method: 'POST' });
  } finally {
    useAuthStore.getState().clear();
    useTenancyStore.getState().clear();
  }
}
