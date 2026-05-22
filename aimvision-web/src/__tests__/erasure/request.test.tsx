import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import { initI18n } from '@/config/i18n';
import { useAuthStore } from '@/state/authStore';
import { ErasureRequestRoute } from '@/routes/app/erasure/request';
import type { Athlete } from '@/services/athletes';
import type { ErasureTicket } from '@/services/erasure';

vi.mock('@/services/athletes', async () => {
  const actual = await vi.importActual('@/services/athletes');
  return { ...actual, listAthletes: vi.fn() };
});

vi.mock('@/services/erasure', async () => {
  const actual = await vi.importActual('@/services/erasure');
  return { ...actual, submitErasure: vi.fn(), executeErasure: vi.fn() };
});

import * as athletesService from '@/services/athletes';
import * as erasureService from '@/services/erasure';

beforeAll(() => {
  initI18n();
});

function renderRoute() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: '/', element: <ErasureRequestRoute /> }], {
    initialEntries: ['/'],
  });
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

const PENDING: ErasureTicket = {
  id: 'erase-1',
  tenantId: 'org:club1',
  athleteUserId: 'ath-1',
  requestedBy: 'coach-1',
  reason: 'Subject withdrew consent',
  status: 'pending',
  references: null,
  createdAt: '2026-05-22T09:00:00Z',
  completedAt: null,
};

const COMPLETED: ErasureTicket = {
  ...PENDING,
  status: 'completed',
  references: { sessions: 3, recordings: 7, shots: 120 },
  completedAt: '2026-05-22T09:01:00Z',
};

function loginAs(role: 'athlete' | 'coach') {
  useAuthStore.getState().setSession('token', {
    userId: 'coach-1',
    tenantId: 'org:club1',
    role,
    displayName: 'Coach',
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(athletesService.listAthletes).mockResolvedValue(ATHLETES);
  vi.mocked(erasureService.submitErasure).mockResolvedValue(PENDING);
  vi.mocked(erasureService.executeErasure).mockResolvedValue(COMPLETED);
  useAuthStore.getState().clear();
});

describe('ErasureRequestRoute', () => {
  it('blocks an athlete principal with an empty-state explanation', async () => {
    loginAs('athlete');
    renderRoute();
    expect(await screen.findByText(/requires a coach or administrator role/i)).toBeInTheDocument();
    expect(athletesService.listAthletes).not.toHaveBeenCalled();
  });

  it('opens a pending ticket, then gates execute behind the confirmation checkbox', async () => {
    const user = userEvent.setup();
    loginAs('coach');
    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Anna Athlete' })).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText(/data subject/i), 'ath-1');
    await user.type(screen.getByLabelText(/reason for erasure/i), 'Subject withdrew consent');
    await user.click(screen.getByRole('button', { name: /open erasure request/i }));

    // Pending ticket card appears.
    expect(await screen.findByText('erase-1')).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(vi.mocked(erasureService.submitErasure).mock.calls[0]?.[0]).toEqual({
      athleteUserId: 'ath-1',
      reason: 'Subject withdrew consent',
    });

    // Execute is disabled until the irreversible-action box is ticked.
    const executeBtn = screen.getByRole('button', { name: /execute erasure/i });
    expect(executeBtn).toBeDisabled();
    expect(erasureService.executeErasure).not.toHaveBeenCalled();

    await user.click(screen.getByRole('checkbox'));
    expect(executeBtn).toBeEnabled();

    await user.click(executeBtn);

    // Completed state shows reference counts.
    expect(await screen.findByText('Completed')).toBeInTheDocument();
    expect(vi.mocked(erasureService.executeErasure).mock.calls[0]?.[0]).toBe('erase-1');
    expect(screen.getByText('sessions')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
  });

  it('surfaces a required-field error when no reason is given', async () => {
    const user = userEvent.setup();
    loginAs('coach');
    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Anna Athlete' })).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText(/data subject/i), 'ath-1');
    // No reason typed. The HTML5 required attribute blocks submit, and even
    // if it didn't, the handler guard MUST prevent the network call.
    await user.click(screen.getByRole('button', { name: /open erasure request/i }));

    expect(erasureService.submitErasure).not.toHaveBeenCalled();
  });
});
