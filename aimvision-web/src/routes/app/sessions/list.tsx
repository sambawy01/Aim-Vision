import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { listSessions, type Session } from '@/services/sessions';
import { EmptyState } from '@/components/EmptyState';

export function SessionListRoute() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery<Session[]>({
    queryKey: ['sessions', 'list'],
    queryFn: listSessions,
    initialData: [],
    retry: false,
  });

  return (
    <section aria-labelledby="sessions-heading">
      <h1 id="sessions-heading" className="text-2xl font-semibold mb-4">
        {t('sessions.title')}
      </h1>
      {isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {isError ? (
        <p role="alert" className="text-danger">
          {t('common.error')}
        </p>
      ) : null}
      {data && data.length > 0 ? (
        <ul className="border border-border rounded-lg bg-surface divide-y divide-border">
          {data.map((s) => (
            <li key={s.id}>
              <Link
                to={`/app/sessions/${s.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-surface-muted focus-visible:bg-surface-muted"
              >
                <span className="font-medium">{s.id}</span>
                <span className="text-sm text-text-muted">
                  {s.shotCount} shots · {s.startedAt}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title={t('sessions.empty')} />
      )}
    </section>
  );
}
