/**
 * Re-export react-i18next's useTranslation alongside RTL helpers.
 */
import { I18nManager } from 'react-native';
import { useTranslation as useI18nTranslation } from 'react-i18next';

export function useTranslation() {
  const { t, i18n } = useI18nTranslation();
  return {
    t,
    i18n,
    isRTL: I18nManager.isRTL,
    locale: i18n.language,
  };
}
