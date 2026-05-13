import { useTranslation } from 'react-i18next';
import type { FederationOverview } from '@/services/federation';

interface OverviewCardProps {
  overview: FederationOverview;
}

/**
 * Top-of-page metric card for the federation dashboard.
 *
 * Four headline numbers: total athletes, active clubs, sessions in the
 * last 30 days, and an engagement rate (avg sessions / athlete / 30d).
 * Engagement rate is colour-coded by federation-defined thresholds:
 *   < 0.5  → low (red)     federation should outreach
 *   < 2.0  → moderate (amber)
 *   >= 2.0 → healthy (green)
 */
export function FederationOverviewCard({ overview }: OverviewCardProps): JSX.Element {
  const { t } = useTranslation();
  const engagementTier =
    overview.engagementRate < 0.5 ? 'low' : overview.engagementRate < 2.0 ? 'moderate' : 'healthy';

  return (
    <section
      aria-labelledby="federation-overview-heading"
      className="border border-border rounded-lg bg-surface p-4"
    >
      <h2 id="federation-overview-heading" className="text-lg font-semibold mb-3">
        {overview.federationName}
      </h2>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Metric label={t('federation.metrics.athletes')} value={overview.athletesTotal} />
        <Metric label={t('federation.metrics.clubs')} value={overview.clubsActive} />
        <Metric label={t('federation.metrics.sessionsLast30d')} value={overview.sessionsLast30d} />
        <Metric
          label={t('federation.metrics.engagement')}
          value={overview.engagementRate.toFixed(2)}
          tier={engagementTier}
        />
      </dl>
    </section>
  );
}

interface MetricProps {
  label: string;
  value: string | number;
  tier?: 'low' | 'moderate' | 'healthy';
}

function Metric({ label, value, tier }: MetricProps): JSX.Element {
  const valueClass =
    tier === 'low'
      ? 'text-danger'
      : tier === 'moderate'
        ? 'text-warning'
        : tier === 'healthy'
          ? 'text-success'
          : 'text-text';
  return (
    <div>
      <dt className="text-sm text-text-muted">{label}</dt>
      <dd className={`text-2xl font-semibold ${valueClass}`}>{value}</dd>
    </div>
  );
}
