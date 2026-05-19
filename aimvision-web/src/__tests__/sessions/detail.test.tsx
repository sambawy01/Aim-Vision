import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import { initI18n } from '@/config/i18n';
import { SessionDetailRoute } from '@/routes/app/sessions/[id]';
import type { Session, SessionSummary } from '@/services/sessions';

vi.mock('@/services/sessions', async () => {
  const actual = await vi.importActual('@/services/sessions');
  return {
    ...actual,
    getSession: vi.fn(),
    getSessionSummary: vi.fn(),
    processSession: vi.fn(),
  };
});

import * as sessionService from '@/services/sessions';

beforeAll(() => {
  initI18n();
});

function renderRoute(sessionId = 'sess-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      {
        path: '/app/sessions/:id',
        element: <SessionDetailRoute />,
      },
      {
        path: '/app/sessions',
        element: <p>list placeholder</p>,
      },
    ],
    { initialEntries: [`/app/sessions/${sessionId}`] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const SESSION: Session = {
  id: 'sess-1',
  orgId: 'org-1',
  athleteId: 'user-1',
  discipline: 'trap',
  startedAt: '2026-05-19T09:00:00Z',
  endedAt: '2026-05-19T09:45:00Z',
  partialSession: false,
};

const SUMMARY: SessionSummary = {
  sessionId: 'sess-1',
  recordingCount: 2,
  shotCount: 25,
  calibrationCount: 2,
  alignmentComplete: true,
  calibrationComplete: true,
  endedAt: '2026-05-19T09:45:00Z',
  partialSession: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(sessionService.getSession).mockResolvedValue(SESSION);
  vi.mocked(sessionService.getSessionSummary).mockResolvedValue(SUMMARY);
  vi.mocked(sessionService.processSession).mockResolvedValue({
    sessionId: 'sess-1',
    workflowId: 'process-session-sess-1-abcd1234',
    taskQueue: 'aimvision-post-session',
  });
});

describe('SessionDetailRoute', () => {
  it('renders detail + summary side-by-side when both endpoints respond', async () => {
    renderRoute();
    // The athlete id is in a <dd> — wait for it as the signal that
    // the detail query has resolved.
    expect(await screen.findByText('user-1')).toBeInTheDocument();
    expect(screen.getByText('trap')).toBeInTheDocument();
    // Summary block
    expect(
      await screen.findByRole('heading', { name: /post-session summary/i }),
    ).toBeInTheDocument();
    // Two metrics in the summary block share the value "2" (recordings
    // + calibrations) so check both with getAllByText, plus the
    // distinctly-valued shot count.
    expect(screen.getAllByText('2', { selector: 'dd' })).toHaveLength(2);
    expect(screen.getByText('25', { selector: 'dd' })).toBeInTheDocument();
    // Readiness chips
    expect(screen.getByLabelText(/alignment: ready/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/calibration: ready/i)).toBeInTheDocument();
  });

  it('shows pending readiness chips when summary booleans are false', async () => {
    vi.mocked(sessionService.getSessionSummary).mockResolvedValue({
      ...SUMMARY,
      alignmentComplete: false,
      calibrationComplete: false,
    });

    renderRoute();
    await waitFor(() => {
      expect(screen.getByLabelText(/alignment: pending/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/calibration: pending/i)).toBeInTheDocument();
  });

  it('renders the partial badge when the session is marked partial', async () => {
    vi.mocked(sessionService.getSession).mockResolvedValue({
      ...SESSION,
      partialSession: true,
    });

    renderRoute();
    await waitFor(() => {
      // The badge uses the aria label for the partial-session announcement.
      expect(screen.getByLabelText(/incomplete diagnostic coverage/i)).toBeInTheDocument();
    });
  });

  it('surfaces a single error region when either query fails', async () => {
    vi.mocked(sessionService.getSession).mockRejectedValue(new Error('boom'));

    renderRoute();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('triggers the post-session pipeline and shows the workflow id', async () => {
    const user = userEvent.setup();
    renderRoute();

    const btn = await screen.findByRole('button', { name: /run post-session pipeline/i });
    await user.click(btn);

    await waitFor(() => {
      expect(sessionService.processSession).toHaveBeenCalledWith('sess-1');
    });
    // The returned workflow id renders in a status region.
    expect(await screen.findByRole('status')).toHaveTextContent('process-session-sess-1-abcd1234');
  });

  it('shows an error when the pipeline trigger fails', async () => {
    const user = userEvent.setup();
    vi.mocked(sessionService.processSession).mockRejectedValueOnce(new Error('boom'));
    renderRoute();

    const btn = await screen.findByRole('button', { name: /run post-session pipeline/i });
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/could not start the pipeline/i)).toBeInTheDocument();
    });
  });
});
