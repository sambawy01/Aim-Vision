import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { listAthletes, type Athlete } from '@/services/athletes';
import { AthleteListItem } from '@/components/AthleteListItem';
import { EmptyState } from '@/components/EmptyState';

export function AthleteListRoute() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery<Athlete[]>({
    queryKey: ['athletes', 'list'],
    queryFn: listAthletes,
    // Placeholder seed for the scaffold; backend not wired yet.
    initialData: [],
    retry: false,
  });

  return (
    <section aria-labelledby="athletes-heading">
      <h1 id="athletes-heading" className="text-2xl font-semibold mb-4">
        {t('athletes.title')}
      </h1>

      {isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {isError ? (
        <p role="alert" className="text-danger">
          {t('common.error')}
        </p>
      ) : null}

      {data && data.length > 0 ? (
        <ul className="border border-border rounded-lg bg-surface divide-y divide-border">
          {data.map((athlete) => (
            <AthleteListItem key={athlete.id} athlete={athlete} />
          ))}
        </ul>
      ) : (
        <EmptyState title={t('athletes.empty')} />
      )}
    </section>
  );
}
