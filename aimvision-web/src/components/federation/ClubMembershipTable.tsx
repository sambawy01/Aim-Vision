import { useTranslation } from 'react-i18next';
import type { ClubMembership } from '@/services/federation';

interface Props {
  clubs: ClubMembership[];
}

/**
 * Cross-club membership table for the federation dashboard.
 *
 * Sortable columns are a later refinement; for the scaffold we render
 * the rows in the order the backend returns them and let federation
 * admins drill into individual clubs by clicking the row.
 */
export function ClubMembershipTable({ clubs }: Props): JSX.Element {
  const { t } = useTranslation();

  if (clubs.length === 0) {
    return (
      <section aria-labelledby="clubs-heading">
        <h2 id="clubs-heading" className="text-lg font-semibold mb-3">
          {t('federation.clubs.title')}
        </h2>
        <p className="text-text-muted">{t('federation.clubs.empty')}</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="clubs-heading">
      <h2 id="clubs-heading" className="text-lg font-semibold mb-3">
        {t('federation.clubs.title')}
      </h2>
      <div className="overflow-x-auto border border-border rounded-lg bg-surface">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-alt text-text-muted">
            <tr>
              <Th>{t('federation.clubs.name')}</Th>
              <Th>{t('federation.clubs.athletes')}</Th>
              <Th>{t('federation.clubs.coaches')}</Th>
              <Th>{t('federation.clubs.lastSession')}</Th>
              <Th>{t('federation.clubs.status')}</Th>
            </tr>
          </thead>
          <tbody>
            {clubs.map((c) => (
              <tr key={c.clubId} className="border-t border-border">
                <Td>{c.clubName}</Td>
                <Td>{c.athletesCount}</Td>
                <Td>{c.coachesCount}</Td>
                <Td>{c.lastSessionAt ? formatDate(c.lastSessionAt) : '—'}</Td>
                <Td>
                  <StatusPill status={c.status} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Th({ children }: { children: React.ReactNode }): JSX.Element {
  return <th className="text-start px-3 py-2 font-medium">{children}</th>;
}
function Td({ children }: { children: React.ReactNode }): JSX.Element {
  return <td className="px-3 py-2">{children}</td>;
}

function StatusPill({ status }: { status: ClubMembership['status'] }): JSX.Element {
  const { t } = useTranslation();
  const classes =
    status === 'active'
      ? 'bg-success/10 text-success'
      : status === 'paused'
        ? 'bg-warning/10 text-warning'
        : 'bg-text-muted/10 text-text-muted';
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs ${classes}`}>
      {t(`federation.clubs.statusLabel.${status}`)}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}
