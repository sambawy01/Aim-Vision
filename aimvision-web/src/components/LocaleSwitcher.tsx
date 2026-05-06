import { useTranslation } from 'react-i18next';
import { SUPPORTED_LOCALES, type SupportedLocale } from '@/config/i18n';

export function LocaleSwitcher() {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage?.split('-')[0] ?? 'en') as SupportedLocale;

  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-text-muted">{t('locale.switcher')}</span>
      <select
        aria-label={t('locale.switcher')}
        value={current}
        onChange={(e) => {
          void i18n.changeLanguage(e.target.value);
        }}
        className="min-h-touch px-3 py-1 rounded-md border border-border bg-surface text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        {SUPPORTED_LOCALES.map((lng) => (
          <option key={lng} value={lng}>
            {t(`locale.${lng}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
