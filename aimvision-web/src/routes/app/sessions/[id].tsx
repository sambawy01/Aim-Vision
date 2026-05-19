import { useParams, Link } from 'react-router-dom';
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  getSession,
  getSessionSummary,
  processSession,
  type ProcessSessionResult,
} from '@/services/sessions';

function ReadinessChip({
  ok,
  label,
}: {
  ok: boolean;
  label: string;
}): JSX.Element {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        ok ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning'
      }`}
      aria-label={`${label}: ${ok ? 'ready' : 'pending'}`}
    >
      {ok ? '✓ ' : '… '}
      {label}
    </span>
  );
}

export function SessionDetailRoute() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();

  // Parallel queries — both hit the same session id but different
  // endpoints; React Query coordinates the fetch + cache.
  const results = useQueries({
    queries: [
      {
        queryKey: ['sessions', 'detail', id],
        queryFn: () => getSession(id),
        enabled: id.length > 0,
        retry: false,
      },
      {
        queryKey: ['sessions', 'summary', id],
        queryFn: () => getSessionSummary(id),
        enabled: id.length > 0,
        retry: false,
      },
    ],
  });
  const [detail, summary] = results;

  const queryClient = useQueryClient();
  const processMutation = useMutation<ProcessSessionResult, unknown, void>({
    mutationFn: () => processSession(id),
    onSuccess: () => {
      // The pipeline will eventually mutate the summary (alignment,
      // calibration, shots). Refetch so the readiness chips reflect
      // progress once the worker commits.
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'summary', id] });
    },
  });

  const isLoading = detail.isLoading || summary.isLoading;
  const isError = detail.isError || summary.isError;

  return (
    <section aria-labelledby="session-detail-heading" className="space-y-4">
      <Link
        to="/app/sessions"
        className="text-sm text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
      >
        ← {t('nav.sessions')}
      </Link>
      <div className="flex items-baseline gap-3">
        <h1 id="session-detail-heading" className="text-2xl font-semibold">
          {detail.data?.id ?? id}
        </h1>
        {detail.data?.partialSession ? (
          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-warning/20 text-warning"
            aria-label={t('sessions.partialBadgeAria')}
          >
            {t('sessions.partialBadge')}
          </span>
        ) : null}
      </div>
      {isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {isError ? (
        <p role="alert" className="text-danger">
          {t('common.error')}
        </p>
      ) : null}
      {detail.data ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-text-muted">{t('sessions.detail.athlete')}</dt>
          <dd className="font-mono">{detail.data.athleteId}</dd>
          <dt className="text-text-muted">{t('sessions.detail.discipline')}</dt>
          <dd>{detail.data.discipline}</dd>
          <dt className="text-text-muted">{t('sessions.detail.started')}</dt>
          <dd>{detail.data.startedAt}</dd>
          <dt className="text-text-muted">{t('sessions.detail.ended')}</dt>
          <dd>{detail.data.endedAt ?? '—'}</dd>
        </dl>
      ) : null}
      {summary.data ? (
        <section
          aria-label={t('sessions.summary.heading')}
          className="border border-border rounded-lg bg-surface p-4 space-y-3"
        >
          <h2 className="text-lg font-medium">{t('sessions.summary.heading')}</h2>
          <dl className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <dt className="text-text-muted">{t('sessions.summary.recordings')}</dt>
              <dd className="text-2xl font-semibold">{summary.data.recordingCount}</dd>
            </div>
            <div>
              <dt className="text-text-muted">{t('sessions.summary.shots')}</dt>
              <dd className="text-2xl font-semibold">{summary.data.shotCount}</dd>
            </div>
            <div>
              <dt className="text-text-muted">{t('sessions.summary.calibrations')}</dt>
              <dd className="text-2xl font-semibold">{summary.data.calibrationCount}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-2">
            <ReadinessChip
              ok={summary.data.alignmentComplete}
              label={t('sessions.summary.alignment')}
            />
            <ReadinessChip
              ok={summary.data.calibrationComplete}
              label={t('sessions.summary.calibration')}
            />
          </div>

          <div className="pt-2 border-t border-border space-y-2">
            <button
              type="button"
              onClick={() => processMutation.mutate()}
              disabled={processMutation.isPending}
              className="rounded bg-brand-accent text-white px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-60"
            >
              {processMutation.isPending
                ? t('common.loading')
                : t('sessions.process.cta')}
            </button>
            {processMutation.isSuccess ? (
              <p className="text-sm text-success" role="status">
                {t('sessions.process.enqueued')}{' '}
                <code className="font-mono text-xs">{processMutation.data.workflowId}</code>
              </p>
            ) : null}
            {processMutation.isError ? (
              <p className="text-sm text-danger" role="alert">
                {t('sessions.process.error')}
              </p>
            ) : null}
          </div>
        </section>
      ) : null}
    </section>
  );
}
