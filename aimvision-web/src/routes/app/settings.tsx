import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { LocaleSwitcher } from '@/components/LocaleSwitcher';
import { useTenancy } from '@/hooks/useTenancy';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/a11y/Button';

export function SettingsRoute() {
  const { t } = useTranslation();
  const { principal } = useAuth();
  const { current } = useTenancy();

  return (
    <section aria-labelledby="settings-heading" className="space-y-6">
      <h1 id="settings-heading" className="text-2xl font-semibold">
        {t('settings.title')}
      </h1>

      <div className="space-y-2">
        <h2 className="text-sm font-medium text-text-muted">{t('settings.language')}</h2>
        <LocaleSwitcher />
      </div>

      <div className="space-y-2">
        <h2 className="text-sm font-medium text-text-muted">{t('settings.tenant')}</h2>
        <p className="font-mono text-sm">{current?.tenantId ?? '—'}</p>
      </div>

      {principal ? (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-text-muted">Principal</h2>
          <p className="text-sm">
            {principal.displayName} · <span className="font-mono">{principal.role}</span>
          </p>
        </div>
      ) : null}

      <Link to="/auth/logout">
        <Button variant="secondary">{t('auth.logout')}</Button>
      </Link>
    </section>
  );
}
