import { Navigate, createBrowserRouter } from 'react-router-dom';
import App from '@/App';
import { useAuthStore } from '@/state/authStore';

import { LoginRoute } from './auth/login';
import { LogoutRoute } from './auth/logout';
import { AppLayout } from './app/layout';
import { AthleteListRoute } from './app/athletes/list';
import { AthleteDetailRoute } from './app/athletes/[id]';
import { SessionListRoute } from './app/sessions/list';
import { SessionCreateRoute } from './app/sessions/new';
import { SessionDetailRoute } from './app/sessions/[id]';
import { CheckinScanRoute } from './app/checkin/scan';
import { FederationDashboardRoute } from './app/federation/dashboard';
import { SettingsRoute } from './app/settings';

function RequireAuth({ children }: { children: JSX.Element }): JSX.Element {
  const isAuthed = useAuthStore((s) => s.accessToken !== null && s.principal !== null);
  if (!isAuthed) return <Navigate to="/auth/login" replace />;
  return children;
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/auth/login" replace /> },
      { path: 'auth/login', element: <LoginRoute /> },
      { path: 'auth/logout', element: <LogoutRoute /> },
      {
        path: 'app',
        element: (
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <Navigate to="/app/athletes" replace /> },
          { path: 'athletes', element: <AthleteListRoute /> },
          { path: 'athletes/:id', element: <AthleteDetailRoute /> },
          { path: 'sessions', element: <SessionListRoute /> },
          { path: 'sessions/new', element: <SessionCreateRoute /> },
          { path: 'sessions/:id', element: <SessionDetailRoute /> },
          { path: 'checkin', element: <CheckinScanRoute /> },
          { path: 'federation', element: <FederationDashboardRoute /> },
          { path: 'settings', element: <SettingsRoute /> },
        ],
      },
      { path: '*', element: <Navigate to="/auth/login" replace /> },
    ],
  },
]);
