import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTenancy } from '@/hooks/useTenancy';
import { switchTenant } from '@/services/auth';
import { useAuthStore } from '@/state/authStore';
import { LocaleSwitcher } from './LocaleSwitcher';

export function AppShell() {
  const { t } = useTranslation();
  const { current, available } = useTenancy();
  const role = useAuthStore((s) => s.principal?.role);
  const isFedAdmin = role === 'federation_admin';
  // Erasure is coach-or-higher; only `athlete` sits below it.
  const canErase = role !== undefined && role !== 'athlete';

  return (
    <div className="min-h-screen bg-surface text-text flex flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-bold text-lg">{t('app.name')}</span>
            {available.length > 0 && current ? (
              <label className="text-sm flex items-center gap-2">
                <span className="sr-only">{t('settings.tenant')}</span>
                <select
                  value={current.tenantId}
                  onChange={(e) => {
                    // Re-mints the token for the target tenant before flipping
                    // scope. On failure `current` is unchanged, so the controlled
                    // select snaps back to the active tenant.
                    void switchTenant(e.target.value).catch(() => undefined);
                  }}
                  aria-label={t('settings.tenant')}
                  className="min-h-touch px-2 py-1 rounded-md border border-border bg-surface text-text"
                >
                  {available.map((m) => (
                    <option key={m.tenantId} value={m.tenantId}>
                      {m.displayName}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          <LocaleSwitcher />
        </div>
        <nav aria-label="Primary" className="mx-auto max-w-6xl px-4 pb-2">
          <ul className="flex gap-4 text-sm">
            <li>
              <NavLink to="/app/athletes" className={navClass}>
                {t('nav.athletes')}
              </NavLink>
            </li>
            <li>
              <NavLink to="/app/sessions" className={navClass}>
                {t('nav.sessions')}
              </NavLink>
            </li>
            <li>
              <NavLink to="/app/checkin" className={navClass}>
                {t('nav.checkin')}
              </NavLink>
            </li>
            {isFedAdmin ? (
              <li>
                <NavLink to="/app/federation" className={navClass}>
                  {t('nav.federation')}
                </NavLink>
              </li>
            ) : null}
            {canErase ? (
              <li>
                <NavLink to="/app/erasure" className={navClass}>
                  {t('nav.erasure')}
                </NavLink>
              </li>
            ) : null}
            <li>
              <NavLink to="/app/settings" className={navClass}>
                {t('nav.settings')}
              </NavLink>
            </li>
          </ul>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-6 flex-1">
        <Outlet />
      </main>
    </div>
  );
}

function navClass({ isActive }: { isActive: boolean }): string {
  const base =
    'inline-block min-h-touch py-2 px-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus';
  return isActive ? `${base} text-brand-accent font-semibold` : `${base} text-text-muted`;
}
