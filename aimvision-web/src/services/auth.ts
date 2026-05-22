import { fetchJson } from './api';
import { queryClient } from '@/config/query';
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

interface SwitchTenantResponse {
  access_token: string;
  principal: PrincipalWire;
}

/**
 * Switch the active tenancy. The access token's `tid` claim binds the session
 * to one tenant, so the backend re-mints the token for the target tenant; we
 * must update the token BEFORE flipping `current` (which drives the
 * `X-Tenant-Scope` header), or the next request would mismatch and 401.
 *
 * Called with the current (old) tenant still active, so the request itself
 * carries a matching token + scope. On success the per-tenant query caches are
 * invalidated so every list refetches under the new scope.
 */
export async function switchTenant(tenantId: string): Promise<void> {
  const body = await fetchJson<SwitchTenantResponse>('/auth/switch-tenant', {
    method: 'POST',
    body: JSON.stringify({ tenant_id: tenantId }),
  });
  useAuthStore.getState().setSession(body.access_token, toPrincipal(body.principal));
  useTenancyStore.getState().switchTo(tenantId);
  await queryClient.invalidateQueries();
}

export async function logout(): Promise<void> {
  try {
    await fetchJson('/auth/logout', { method: 'POST' });
  } finally {
    useAuthStore.getState().clear();
    useTenancyStore.getState().clear();
  }
}
