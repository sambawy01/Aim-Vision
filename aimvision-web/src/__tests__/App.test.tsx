import { describe, it, expect, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import App from '@/App';
import { initI18n } from '@/config/i18n';
import { LoginRoute } from '@/routes/auth/login';
import { useAuthStore } from '@/state/authStore';

beforeAll(() => {
  initI18n();
});

function renderApp(initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <App />,
        children: [
          { index: true, element: <LoginRoute /> },
          { path: 'auth/login', element: <LoginRoute /> },
        ],
      },
    ],
    { initialEntries },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe('App', () => {
  it('renders the login screen by default when unauthenticated', () => {
    useAuthStore.getState().clear();
    renderApp(['/']);
    expect(screen.getByRole('heading', { name: /sign in to aimvision/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });
});
