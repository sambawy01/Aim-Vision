import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getSession } from '@/services/sessions';

export function SessionDetailRoute() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sessions', 'detail', id],
    queryFn: () => getSession(id),
    enabled: id.length > 0,
    retry: false,
  });

  return (
    <section aria-labelledby="session-detail-heading" className="space-y-4">
      <Link
        to="/app/sessions"
        className="text-sm text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
      >
        ← {t('nav.sessions')}
      </Link>
      <h1 id="session-detail-heading" className="text-2xl font-semibold">
        {data?.id ?? id}
      </h1>
      {isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {isError ? (
        <p role="alert" className="text-danger">
          {t('common.error')}
        </p>
      ) : null}
      {data ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-text-muted">athlete</dt>
          <dd className="font-mono">{data.athleteId}</dd>
          <dt className="text-text-muted">started</dt>
          <dd>{data.startedAt}</dd>
          <dt className="text-text-muted">ended</dt>
          <dd>{data.endedAt ?? '—'}</dd>
          <dt className="text-text-muted">shots</dt>
          <dd>{data.shotCount}</dd>
        </dl>
      ) : null}
    </section>
  );
}
