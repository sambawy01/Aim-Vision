import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { listAthletes, type Athlete } from '@/services/athletes';
import { executeErasure, submitErasure, type ErasureTicket } from '@/services/erasure';
import { ApiError } from '@/services/api';
import { useAuthStore } from '@/state/authStore';
import { EmptyState } from '@/components/EmptyState';

/** Roles permitted to file an erasure request. Mirrors the backend
 * `require_role("coach")` gate (coach-or-higher); only `athlete`
 * sits below it in the hierarchy. */
const ERASURE_ROLES = new Set(['coach', 'club_admin', 'federation_admin', 'system_admin']);

/**
 * /app/erasure — coach/admin files a right-to-erasure request (GDPR Art. 17)
 * on behalf of a data subject, then executes the crypto-shred.
 *
 * Two phases share one route:
 *   1. Request form — pick athlete + reason → POST /erasure (status pending).
 *   2. Ticket card — shows the pending ticket and a danger-zone execute
 *      action. Execution permanently destroys the subject's data, so it is
 *      gated behind an explicit "I understand" confirmation before the
 *      POST /erasure/{id}/execute fires.
 */
export function ErasureRequestRoute(): JSX.Element {
  const { t } = useTranslation();
  const role = useAuthStore((s) => s.principal?.role);

  const [athleteId, setAthleteId] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [ticket, setTicket] = useState<ErasureTicket | null>(null);

  const athletesQuery = useQuery<Athlete[]>({
    queryKey: ['athletes', 'list'],
    queryFn: listAthletes,
    initialData: [],
    retry: false,
    enabled: role !== undefined && ERASURE_ROLES.has(role),
  });

  const submitMutation = useMutation({
    mutationFn: submitErasure,
    onSuccess: (created) => {
      setTicket(created);
      setError(null);
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? t('erasure.errors.submitWithStatus', { status: err.status })
          : t('common.error'),
      );
    },
  });

  const executeMutation = useMutation({
    mutationFn: executeErasure,
    onSuccess: (done) => {
      setTicket(done);
      setError(null);
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? t('erasure.errors.executeWithStatus', { status: err.status })
          : t('common.error'),
      );
    },
  });

  if (role !== undefined && !ERASURE_ROLES.has(role)) {
    return (
      <section aria-labelledby="erasure-heading">
        <h1 id="erasure-heading" className="text-2xl font-semibold mb-4">
          {t('erasure.title')}
        </h1>
        <EmptyState title={t('erasure.notAllowed')} />
      </section>
    );
  }

  function onSubmit(e: React.FormEvent): void {
    e.preventDefault();
    setError(null);
    if (!athleteId || reason.trim().length === 0) {
      setError(t('erasure.errors.required'));
      return;
    }
    submitMutation.mutate({ athleteUserId: athleteId, reason: reason.trim() });
  }

  function reset(): void {
    setTicket(null);
    setAthleteId('');
    setReason('');
    setConfirmed(false);
    setError(null);
  }

  return (
    <section aria-labelledby="erasure-heading" className="space-y-4 max-w-lg">
      <header>
        <h1 id="erasure-heading" className="text-2xl font-semibold">
          {t('erasure.title')}
        </h1>
        <p className="text-text-muted">{t('erasure.subtitle')}</p>
      </header>

      {ticket === null ? (
        <form
          onSubmit={onSubmit}
          className="space-y-4 border border-border rounded-lg bg-surface p-4"
        >
          <div>
            <label htmlFor="athlete" className="block text-sm font-medium mb-1">
              {t('erasure.athlete')}
            </label>
            <select
              id="athlete"
              required
              value={athleteId}
              onChange={(e) => setAthleteId(e.target.value)}
              className="block w-full rounded border border-border bg-surface px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              disabled={athletesQuery.isLoading}
            >
              <option value="" disabled>
                {athletesQuery.isLoading ? t('common.loading') : t('erasure.athletePlaceholder')}
              </option>
              {athletesQuery.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.displayName}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="reason" className="block text-sm font-medium mb-1">
              {t('erasure.reason')}
            </label>
            <textarea
              id="reason"
              required
              maxLength={255}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t('erasure.reasonPlaceholder')}
              className="block w-full rounded border border-border bg-surface px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            />
          </div>

          {error ? (
            <p role="alert" className="text-danger text-sm">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitMutation.isPending}
            className="rounded bg-brand-accent text-white px-4 py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-60"
          >
            {submitMutation.isPending ? t('common.loading') : t('erasure.submit')}
          </button>
        </form>
      ) : (
        <div className="space-y-4 border border-border rounded-lg bg-surface p-4">
          <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-text-muted">{t('erasure.ticket.id')}</dt>
            <dd className="font-mono">{ticket.id}</dd>
            <dt className="text-text-muted">{t('erasure.ticket.athlete')}</dt>
            <dd>{ticket.athleteUserId}</dd>
            <dt className="text-text-muted">{t('erasure.ticket.reason')}</dt>
            <dd>{ticket.reason}</dd>
            <dt className="text-text-muted">{t('erasure.ticket.status')}</dt>
            <dd>
              <span
                className={
                  ticket.status === 'completed'
                    ? 'inline-block rounded px-2 py-0.5 text-xs font-medium bg-success/15 text-success'
                    : 'inline-block rounded px-2 py-0.5 text-xs font-medium bg-surface-muted text-text-muted'
                }
              >
                {t(`erasure.statusLabel.${ticket.status}`)}
              </span>
            </dd>
          </dl>

          {ticket.status === 'pending' ? (
            <div className="border border-danger/40 rounded-md p-3 space-y-3">
              <p className="text-sm font-medium text-danger">{t('erasure.danger.heading')}</p>
              <p className="text-sm text-text-muted">{t('erasure.danger.body')}</p>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  className="mt-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                />
                <span>{t('erasure.danger.confirm')}</span>
              </label>
              {error ? (
                <p role="alert" className="text-danger text-sm">
                  {error}
                </p>
              ) : null}
              <button
                type="button"
                disabled={!confirmed || executeMutation.isPending}
                onClick={() => executeMutation.mutate(ticket.id)}
                className="rounded bg-danger text-white px-4 py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-60"
              >
                {executeMutation.isPending ? t('common.loading') : t('erasure.danger.execute')}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <p role="status" className="text-sm text-success">
                {t('erasure.done.body')}
              </p>
              {ticket.references && Object.keys(ticket.references).length > 0 ? (
                <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
                  {Object.entries(ticket.references).map(([kind, count]) => (
                    <div key={kind} className="contents">
                      <dt className="text-text-muted">{kind}</dt>
                      <dd className="font-mono">{count}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              <button
                type="button"
                onClick={reset}
                className="rounded border border-border px-4 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                {t('erasure.done.another')}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
