import { create } from 'zustand';

/**
 * Auth state.
 *
 * - `accessToken` is held in memory only. The refresh token is set as an
 *   httpOnly cookie by the backend and is never accessible from JS.
 * - `principal` is the current (user, tenant, role) tuple per
 *   docs/security/multi-tenant-isolation.md §1.1.
 *
 * On 401, services/api.ts calls /auth/refresh which mints a new access token
 * and writes it back into this store via `setSession`.
 */

export interface Principal {
  userId: string;
  tenantId: string;
  role: 'athlete' | 'coach' | 'club_admin' | 'federation_admin' | 'system_admin';
  displayName: string;
}

export interface AuthState {
  accessToken: string | null;
  principal: Principal | null;
  setSession: (token: string, principal: Principal) => void;
  setAccessToken: (token: string | null) => void;
  clear: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  principal: null,
  setSession: (token, principal) => set({ accessToken: token, principal }),
  setAccessToken: (token) => set({ accessToken: token }),
  clear: () => set({ accessToken: null, principal: null }),
  isAuthenticated: () => get().accessToken !== null && get().principal !== null,
}));
