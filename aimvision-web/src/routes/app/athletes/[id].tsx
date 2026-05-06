import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getAthlete } from '@/services/athletes';

export function AthleteDetailRoute() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['athletes', 'detail', id],
    queryFn: () => getAthlete(id),
    enabled: id.length > 0,
    retry: false,
  });

  return (
    <section aria-labelledby="athlete-detail-heading" className="space-y-4">
      <Link
        to="/app/athletes"
        className="text-sm text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
      >
        ← {t('nav.athletes')}
      </Link>
      <h1 id="athlete-detail-heading" className="text-2xl font-semibold">
        {data?.displayName ?? id}
      </h1>
      {isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {isError ? (
        <p role="alert" className="text-danger">
          {t('common.error')}
        </p>
      ) : null}
      {data ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-text-muted">id</dt>
          <dd className="font-mono">{data.id}</dd>
          <dt className="text-text-muted">email</dt>
          <dd>{data.email ?? '—'}</dd>
          <dt className="text-text-muted">joined</dt>
          <dd>{data.joinedAt}</dd>
        </dl>
      ) : null}
    </section>
  );
}
