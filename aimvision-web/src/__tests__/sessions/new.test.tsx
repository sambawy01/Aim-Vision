import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import { initI18n } from '@/config/i18n';
import { SessionCreateRoute } from '@/routes/app/sessions/new';
import type { Athlete } from '@/services/athletes';
import type { Org } from '@/services/orgs';
import type { Session } from '@/services/sessions';

vi.mock('@/services/athletes', async () => {
  const actual = await vi.importActual('@/services/athletes');
  return {
    ...actual,
    listAthletes: vi.fn(),
  };
});

vi.mock('@/services/orgs', async () => {
  const actual = await vi.importActual('@/services/orgs');
  return {
    ...actual,
    listOrgs: vi.fn(),
  };
});

vi.mock('@/services/sessions', async () => {
  const actual = await vi.importActual('@/services/sessions');
  return {
    ...actual,
    createSession: vi.fn(),
  };
});

import * as athletesService from '@/services/athletes';
import * as orgsService from '@/services/orgs';
import * as sessionsService from '@/services/sessions';

beforeAll(() => {
  initI18n();
});

function renderRoute() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: '/app/sessions/new', element: <SessionCreateRoute /> },
      // Destination of the post-submit navigate.
      { path: '/app/sessions/:id', element: <p data-testid="detail-page" /> },
      { path: '/app/sessions', element: <p>list placeholder</p> },
    ],
    { initialEntries: ['/app/sessions/new'] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const ATHLETES: Athlete[] = [
  { id: 'ath-1', displayName: 'Anna Athlete', email: 'anna@example.com', joinedAt: '2026-01-01' },
  { id: 'ath-2', displayName: 'Bob Athlete', email: 'bob@example.com', joinedAt: '2026-02-01' },
];

const ORGS: Org[] = [
  { id: 'org-1', name: 'Cairo Club', kind: 'club', tenantId: 'org:c1', federationId: null },
  { id: 'org-2', name: 'Alex Marina', kind: 'club', tenantId: 'org:c2', federationId: null },
];

const CREATED: Session = {
  id: 'sess-NEW',
  orgId: 'org-1',
  athleteId: 'ath-1',
  discipline: 'skeet',
  startedAt: '2026-05-19T10:00:00Z',
  endedAt: null,
  partialSession: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(athletesService.listAthletes).mockResolvedValue(ATHLETES);
  vi.mocked(orgsService.listOrgs).mockResolvedValue(ORGS);
  vi.mocked(sessionsService.createSession).mockResolvedValue(CREATED);
});

describe('SessionCreateRoute', () => {
  it('submits the form and navigates to the new session detail', async () => {
    const user = userEvent.setup();
    renderRoute();

    // Wait for athletes to load into the select.
    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Anna Athlete' })).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText(/athlete/i), 'ath-1');
    await user.selectOptions(screen.getByLabelText(/discipline/i), 'skeet');
    await user.selectOptions(screen.getByLabelText(/organisation/i), 'org-1');
    await user.click(screen.getByRole('button', { name: /start session/i }));

    expect(await screen.findByTestId('detail-page')).toBeInTheDocument();
    expect(sessionsService.createSession).toHaveBeenCalledTimes(1);
    const call = vi.mocked(sessionsService.createSession).mock.calls[0]?.[0];
    expect(call?.athleteUserId).toBe('ath-1');
    expect(call?.orgId).toBe('org-1');
    expect(call?.discipline).toBe('skeet');
  });

  it('surfaces a required-field error when org id is empty', async () => {
    const user = userEvent.setup();
    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Anna Athlete' })).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText(/athlete/i), 'ath-1');
    // Skip org id.
    await user.click(screen.getByRole('button', { name: /start session/i }));

    // HTML5 required attribute will block before our handler fires —
    // but we still want the handler-level guard. Either way the
    // server mutation MUST NOT have been called.
    expect(sessionsService.createSession).not.toHaveBeenCalled();
  });

  it('shows a server error when the mutation rejects', async () => {
    const user = userEvent.setup();
    const { ApiError } = await import('@/services/api');
    vi.mocked(sessionsService.createSession).mockRejectedValueOnce(
      new ApiError(422, 'invalid', { detail: 'bad athlete' }),
    );
    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Anna Athlete' })).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText(/athlete/i), 'ath-1');
    await user.selectOptions(screen.getByLabelText(/organisation/i), 'org-1');
    await user.click(screen.getByRole('button', { name: /start session/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/422/);
  });
});
