import { create } from 'zustand';

/**
 * Tracks the currently active tenancy scope.
 * Per docs/security/multi-tenant-isolation.md §1.1, every request carries
 * `X-Tenant-Scope: <tenant_id>`. This store is the single source of truth
 * for which tenant the UI is operating in.
 */

export type TenantId = string; // e.g. "solo:u_01...", "org:c_01...", "fed:f_01..."
export type TenantRole = 'athlete' | 'coach' | 'club_admin' | 'fed_admin' | 'system_admin';

export interface TenantMembership {
  tenantId: TenantId;
  displayName: string;
  role: TenantRole;
}

export interface TenancyState {
  current: TenantMembership | null;
  available: TenantMembership[];
  setMemberships: (m: TenantMembership[]) => void;
  switchTo: (tenantId: TenantId) => void;
  clear: () => void;
}

export const useTenancyStore = create<TenancyState>((set) => ({
  current: null,
  available: [],
  setMemberships: (memberships) =>
    set({
      available: memberships,
      current: memberships[0] ?? null,
    }),
  switchTo: (tenantId) =>
    set((state) => {
      const next = state.available.find((m) => m.tenantId === tenantId);
      return next ? { current: next } : {};
    }),
  clear: () => set({ current: null, available: [] }),
}));
