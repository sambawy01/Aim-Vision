import { fetchJson } from './api';
import { useAuthStore, type Principal } from '@/state/authStore';
import { useTenancyStore, type TenantMembership } from '@/state/tenancyStore';

/** Wire shapes match the backend's snake_case PrincipalOut / MembershipOut. */
interface PrincipalWire {
  user_id: string;
  tenant_id: string;
  role: Principal['role'];
  display_name: string;
}

interface MembershipWire {
  tenant_id: string;
  display_name: string;
  role: TenantMembership['role'];
}

interface LoginResponse {
  access_token: string;
  principal: PrincipalWire;
  memberships: MembershipWire[];
}

function toPrincipal(w: PrincipalWire): Principal {
  return {
    userId: w.user_id,
    tenantId: w.tenant_id,
    role: w.role,
    displayName: w.display_name,
  };
}

function toMembership(w: MembershipWire): TenantMembership {
  return { tenantId: w.tenant_id, displayName: w.display_name, role: w.role };
}

export async function login(email: string, password: string): Promise<void> {
  const body = await fetchJson<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  useAuthStore.getState().setSession(body.access_token, toPrincipal(body.principal));
  useTenancyStore.getState().setMemberships(body.memberships.map(toMembership));
}

export async function logout(): Promise<void> {
  try {
    await fetchJson('/auth/logout', { method: 'POST' });
  } finally {
    useAuthStore.getState().clear();
    useTenancyStore.getState().clear();
  }
}
