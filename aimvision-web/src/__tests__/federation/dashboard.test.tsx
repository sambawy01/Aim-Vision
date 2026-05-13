import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import { initI18n } from '@/config/i18n';
import { useAuthStore } from '@/state/authStore';
import { FederationDashboardRoute } from '@/routes/app/federation/dashboard';
import type { ClubMembership, FederationOverview } from '@/services/federation';

vi.mock('@/services/federation', async () => {
  const actual = await vi.importActual('@/services/federation');
  return {
    ...actual,
    getFederationOverview: vi.fn(),
    listFederationClubs: vi.fn(),
  };
});

import * as fedService from '@/services/federation';

beforeAll(() => {
  initI18n();
});

function renderRoute() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: '/', element: <FederationDashboardRoute /> }], {
    initialEntries: ['/'],
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const OVERVIEW: FederationOverview = {
  federationId: 'fed-1',
  federationName: 'Egypt National Shooting Federation',
  athletesTotal: 142,
  clubsActive: 6,
  sessionsLast30d: 380,
  engagementRate: 2.68,
  talentCohorts: [
    { id: 'c1', name: 'U21 Trap', athletesCount: 12, medianSessionsPer30d: 4.5 },
    { id: 'c2', name: 'Senior Skeet', athletesCount: 8, medianSessionsPer30d: 1.2 },
  ],
};

const CLUBS: ClubMembership[] = [
  {
    clubId: 'club-1',
    clubName: 'Cairo Shooting Club',
    athletesCount: 60,
    coachesCount: 4,
    lastSessionAt: '2026-05-12T14:00:00Z',
    status: 'active',
  },
  {
    clubId: 'club-2',
    clubName: 'Alexandria Marina Range',
    athletesCount: 22,
    coachesCount: 2,
    lastSessionAt: null,
    status: 'pending_setup',
  },
];

beforeEach(() => {
  vi.mocked(fedService.getFederationOverview).mockResolvedValue(OVERVIEW);
  vi.mocked(fedService.listFederationClubs).mockResolvedValue(CLUBS);
  useAuthStore.getState().clear();
});

describe('FederationDashboardRoute', () => {
  it('blocks non-fed_admin principals with an empty-state explanation', async () => {
    useAuthStore.getState().setSession('token', {
      userId: 'u1',
      tenantId: 'org:club1',
      role: 'coach',
      displayName: 'Coach',
    });
    renderRoute();
    expect(
      await screen.findByText(/only available to federation administrators/i),
    ).toBeInTheDocument();
    expect(fedService.getFederationOverview).not.toHaveBeenCalled();
  });

  it('renders headline metrics for a fed_admin', async () => {
    useAuthStore.getState().setSession('token', {
      userId: 'u1',
      tenantId: 'fed:egypt',
      role: 'fed_admin',
      displayName: 'Fed Admin',
    });
    renderRoute();

    expect(await screen.findByText('Egypt National Shooting Federation')).toBeInTheDocument();
    expect(screen.getByText('142')).toBeInTheDocument(); // athletes
    expect(screen.getByText('6')).toBeInTheDocument(); // clubs
    expect(screen.getByText('380')).toBeInTheDocument(); // sessions
    expect(screen.getByText('2.68')).toBeInTheDocument(); // engagement
  });

  it('marks under-training cohorts (median < 2 sessions / athlete) visibly', async () => {
    useAuthStore.getState().setSession('token', {
      userId: 'u1',
      tenantId: 'fed:egypt',
      role: 'fed_admin',
      displayName: 'Fed Admin',
    });
    renderRoute();

    // The "1.2" cohort median value gets the danger class; we assert
    // the element exists with the styling intent (text-danger).
    const lowMedian = await screen.findByText('1.2');
    expect(lowMedian.className).toMatch(/text-danger/);
    const healthyMedian = screen.getByText('4.5');
    expect(healthyMedian.className).not.toMatch(/text-danger/);
  });

  it('renders the club table with status pills and a placeholder for null lastSessionAt', async () => {
    useAuthStore.getState().setSession('token', {
      userId: 'u1',
      tenantId: 'fed:egypt',
      role: 'fed_admin',
      displayName: 'Fed Admin',
    });
    renderRoute();

    await waitFor(() => {
      expect(screen.getByText('Cairo Shooting Club')).toBeInTheDocument();
    });
    expect(screen.getByText('Alexandria Marina Range')).toBeInTheDocument();
    // Status pill labels render from i18n.
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Setup pending')).toBeInTheDocument();
    // Null last_session_at renders as em dash placeholder.
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
