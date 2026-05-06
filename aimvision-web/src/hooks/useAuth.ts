import { useAuthStore } from '@/state/authStore';

export function useAuth() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const principal = useAuthStore((s) => s.principal);
  const setSession = useAuthStore((s) => s.setSession);
  const clear = useAuthStore((s) => s.clear);
  return {
    accessToken,
    principal,
    isAuthenticated: accessToken !== null && principal !== null,
    setSession,
    clear,
  };
}
