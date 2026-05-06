import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { logout } from '@/services/auth';
import { useAuthStore } from '@/state/authStore';

export function LogoutRoute() {
  const isAuthed = useAuthStore((s) => s.accessToken !== null);

  useEffect(() => {
    if (isAuthed) {
      void logout();
    }
  }, [isAuthed]);

  return <Navigate to="/auth/login" replace />;
}
