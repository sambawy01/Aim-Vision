import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  type ClubMembership,
  type FederationOverview,
  getFederationOverview,
  listFederationClubs,
} from '@/services/federation';
import { useAuthStore } from '@/state/authStore';
import { FederationOverviewCard } from '@/components/federation/OverviewCard';
import { ClubMembershipTable } from '@/components/federation/ClubMembershipTable';
import { TalentCohortGrid } from '@/components/federation/TalentCohortGrid';
import { EmptyState } from '@/components/EmptyState';

/**
 * Sprint 4 EPIC 4.5: federation tier dashboard.
 *
 * Wiring is feature-gated on the principal's role — only `federation_admin`
 * sees the route, and even then the data layer is React Query so when
 * the backend `/v1/federation/*` endpoints land, the page lights up
 * without further client work.
 */
export function FederationDashboardRoute(): JSX.Element {
  const { t } = useTranslation();
  const principal = useAuthStore((s) => s.principal);

  const overviewQ = useQuery<FederationOverview>({
    queryKey: ['federation', 'overview'],
    queryFn: getFederationOverview,
    retry: false,
    enabled: principal?.role === 'federation_admin',
  });

  const clubsQ = useQuery<ClubMembership[]>({
    queryKey: ['federation', 'clubs'],
    queryFn: listFederationClubs,
    retry: false,
    initialData: [],
    enabled: principal?.role === 'federation_admin',
  });

  if (principal?.role !== 'federation_admin') {
    return (
      <section aria-labelledby="federation-heading">
        <h1 id="federation-heading" className="text-2xl font-semibold mb-4">
          {t('federation.title')}
        </h1>
        <EmptyState title={t('federation.notAllowed')} />
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">{t('federation.title')}</h1>
        <p className="text-text-muted">{t('federation.subtitle')}</p>
      </header>

      {overviewQ.isLoading ? <p className="text-text-muted">{t('common.loading')}</p> : null}
      {overviewQ.isError ? (
        <p role="alert" className="text-danger">
          {t('federation.errors.overview')}
        </p>
      ) : null}
      {overviewQ.data ? <FederationOverviewCard overview={overviewQ.data} /> : null}

      {overviewQ.data ? <TalentCohortGrid cohorts={overviewQ.data.talentCohorts} /> : null}

      <ClubMembershipTable clubs={clubsQ.data ?? []} />
    </div>
  );
}
