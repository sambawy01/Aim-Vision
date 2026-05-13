import { useTranslation } from 'react-i18next';
import type { TalentCohort } from '@/services/federation';

interface Props {
  cohorts: TalentCohort[];
}

/**
 * Talent cohort grid. Federation admins use this view to spot
 * under-training cohorts (low median sessions per athlete) before they
 * lose competitive readiness. The threshold here is intentionally
 * generous; federations tune their own per docs/AIMVISION_V2_Sprint_Plan
 * §EPIC 4.5.
 */
export function TalentCohortGrid({ cohorts }: Props): JSX.Element {
  const { t } = useTranslation();
  if (cohorts.length === 0) {
    return (
      <section aria-labelledby="cohorts-heading">
        <h2 id="cohorts-heading" className="text-lg font-semibold mb-3">
          {t('federation.cohorts.title')}
        </h2>
        <p className="text-text-muted">{t('federation.cohorts.empty')}</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="cohorts-heading">
      <h2 id="cohorts-heading" className="text-lg font-semibold mb-3">
        {t('federation.cohorts.title')}
      </h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cohorts.map((c) => (
          <li
            key={c.id}
            className="border border-border rounded-lg bg-surface p-3 flex flex-col gap-1"
          >
            <h3 className="font-semibold">{c.name}</h3>
            <p className="text-sm text-text-muted">
              {t('federation.cohorts.athletesCount', { count: c.athletesCount })}
            </p>
            <p className="text-sm">
              <span className="text-text-muted">{t('federation.cohorts.medianSessions')}: </span>
              <span
                className={
                  c.medianSessionsPer30d < 2
                    ? 'font-semibold text-danger'
                    : 'font-semibold text-text'
                }
              >
                {c.medianSessionsPer30d.toFixed(1)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
