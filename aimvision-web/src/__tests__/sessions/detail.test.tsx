import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

import { initI18n } from '@/config/i18n';
import { SessionDetailRoute } from '@/routes/app/sessions/[id]';
import type { CoachingNote, Session, SessionSummary } from '@/services/sessions';

vi.mock('@/services/sessions', async () => {
  const actual = await vi.importActual('@/services/sessions');
  return {
    ...actual,
    getSession: vi.fn(),
    getSessionSummary: vi.fn(),
    getCoachingNote: vi.fn(),
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

const COACHING_NOTE: CoachingNote = {
  id: 'note-1',
  sessionId: 'sess-1',
  headline: 'Solid session — head lift on the left stations is the next fix.',
  verifierPassed: true,
  degraded: false,
  modelVersion: 'kimi-k2.6@1',
  generatedAt: '2026-05-21T05:41:37+00:00',
  note: {
    headline: 'Solid session — head lift on the left stations is the next fix.',
    top_diagnostics: [
      {
        category: 'head_lift',
        confidence: 0.81,
        coaching_action: 'Cheek to the stock through the break; 10 bead-stare reps.',
        evidence_shot_ids: ['shot_12', 'shot_19'],
      },
    ],
    recommended_drills: ['drill_bead_stare'],
    tone_mode: 'coach',
    language: 'en-US',
    degraded: false,
    verifier_passed: true,
    confidence_overall: 0.74,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(sessionService.getSession).mockResolvedValue(SESSION);
  vi.mocked(sessionService.getSessionSummary).mockResolvedValue(SUMMARY);
  // Default: no coaching note yet (404-equivalent rejection).
  vi.mocked(sessionService.getCoachingNote).mockRejectedValue(new Error('404'));
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

  it('renders the coaching note with diagnostics + drills when present', async () => {
    vi.mocked(sessionService.getCoachingNote).mockResolvedValue(COACHING_NOTE);
    renderRoute();

    expect(await screen.findByRole('heading', { name: /coaching note/i })).toBeInTheDocument();
    expect(screen.getByText(/head lift on the left stations is the next fix/i)).toBeInTheDocument();
    // Diagnostic atom + confidence + action.
    expect(screen.getByText('head_lift')).toBeInTheDocument();
    expect(screen.getByText(/81%/)).toBeInTheDocument();
    expect(screen.getByText(/bead-stare reps/i)).toBeInTheDocument();
    // Recommended drill chip.
    expect(screen.getByText('drill_bead_stare')).toBeInTheDocument();
    // Model attribution.
    expect(screen.getByText(/kimi-k2\.6@1/)).toBeInTheDocument();
  });

  it('omits the coaching-note section when none exists (404)', async () => {
    // Default mock rejects (no note). The page still renders without error.
    renderRoute();
    expect(await screen.findByText('user-1')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /coaching note/i })).not.toBeInTheDocument();
    // A missing note must NOT trip the page-level error region.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the degraded badge on a degraded coaching note', async () => {
    vi.mocked(sessionService.getCoachingNote).mockResolvedValue({
      ...COACHING_NOTE,
      degraded: true,
      note: { ...COACHING_NOTE.note, top_diagnostics: [], recommended_drills: [], degraded: true },
    });
    renderRoute();
    await waitFor(() => {
      expect(screen.getByLabelText(/coaching analysis was degraded/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/no diagnostics surfaced/i)).toBeInTheDocument();
  });
});
