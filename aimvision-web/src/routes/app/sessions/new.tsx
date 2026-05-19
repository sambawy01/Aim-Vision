import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { listAthletes, type Athlete } from '@/services/athletes';
import { listOrgs, type Org } from '@/services/orgs';
import { createSession } from '@/services/sessions';
import { ApiError } from '@/services/api';

const DISCIPLINES = ['trap', 'skeet', 'sporting'] as const;
type Discipline = (typeof DISCIPLINES)[number];

/**
 * /app/sessions/new — coach picks an athlete + org + discipline,
 * server stamps started_at. On success the coach lands on the new
 * session's detail page so they can immediately upload recordings.
 *
 * Both pickers (athlete + org) hit dedicated backend endpoints —
 * GET /athletes (PR #67) and GET /orgs — and are tenant-scoped on
 * the server side. The coach never types an id by hand.
 */
export function SessionCreateRoute(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [athleteId, setAthleteId] = useState('');
  const [orgId, setOrgId] = useState('');
  const [discipline, setDiscipline] = useState<Discipline>('trap');
  const [error, setError] = useState<string | null>(null);

  const athletesQuery = useQuery<Athlete[]>({
    queryKey: ['athletes', 'list'],
    queryFn: listAthletes,
    initialData: [],
    retry: false,
  });

  const orgsQuery = useQuery<Org[]>({
    queryKey: ['orgs', 'list'],
    queryFn: listOrgs,
    initialData: [],
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: createSession,
    onSuccess: (session) => {
      // Bust the sessions list cache so the new row appears the
      // moment the coach hits Back.
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] });
      navigate(`/app/sessions/${session.id}`);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(t('sessions.new.errors.serverWithStatus', { status: err.status }));
      } else {
        setError(t('common.error'));
      }
    },
  });

  function onSubmit(e: React.FormEvent): void {
    e.preventDefault();
    setError(null);
    if (!athleteId || !orgId) {
      setError(t('sessions.new.errors.required'));
      return;
    }
    mutation.mutate({ athleteUserId: athleteId, orgId, discipline });
  }

  return (
    <section aria-labelledby="new-session-heading" className="space-y-4 max-w-lg">
      <Link
        to="/app/sessions"
        className="text-sm text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
      >
        ← {t('nav.sessions')}
      </Link>
      <h1 id="new-session-heading" className="text-2xl font-semibold">
        {t('sessions.new.title')}
      </h1>
      <form
        onSubmit={onSubmit}
        className="space-y-4 border border-border rounded-lg bg-surface p-4"
      >
        <div>
          <label htmlFor="athlete" className="block text-sm font-medium mb-1">
            {t('sessions.new.athlete')}
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
              {athletesQuery.isLoading ? t('common.loading') : t('sessions.new.athletePlaceholder')}
            </option>
            {athletesQuery.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.displayName}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="discipline" className="block text-sm font-medium mb-1">
            {t('sessions.new.discipline')}
          </label>
          <select
            id="discipline"
            value={discipline}
            onChange={(e) => setDiscipline(e.target.value as Discipline)}
            className="block w-full rounded border border-border bg-surface px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {DISCIPLINES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="orgId" className="block text-sm font-medium mb-1">
            {t('sessions.new.org')}
          </label>
          <select
            id="orgId"
            required
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
            className="block w-full rounded border border-border bg-surface px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            disabled={orgsQuery.isLoading}
          >
            <option value="" disabled>
              {orgsQuery.isLoading ? t('common.loading') : t('sessions.new.orgPlaceholder')}
            </option>
            {orgsQuery.data?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name} ({o.kind})
              </option>
            ))}
          </select>
        </div>

        {error ? (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded bg-brand-accent text-white px-4 py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-60"
          >
            {mutation.isPending ? t('common.loading') : t('sessions.new.submit')}
          </button>
          <Link
            to="/app/sessions"
            className="rounded border border-border px-4 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {t('common.cancel')}
          </Link>
        </div>
      </form>
    </section>
  );
}
