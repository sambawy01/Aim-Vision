import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import en from '@/locales/en/common.json';
import ar from '@/locales/ar/common.json';

export const SUPPORTED_LOCALES = ['en', 'ar'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const RTL_LOCALES = new Set<SupportedLocale>(['ar']);

let initialized = false;

export function initI18n(): typeof i18n {
  if (initialized) return i18n;
  initialized = true;

  void i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: {
        en: { common: en },
        ar: { common: ar },
      },
      fallbackLng: 'en',
      supportedLngs: [...SUPPORTED_LOCALES],
      defaultNS: 'common',
      interpolation: { escapeValue: false },
      detection: {
        order: ['querystring', 'localStorage', 'navigator', 'htmlTag'],
        caches: ['localStorage'],
      },
    });

  applyDirection(i18n.language);
  i18n.on('languageChanged', applyDirection);

  return i18n;
}

function applyDirection(lng: string): void {
  if (typeof document === 'undefined') return;
  const base = (lng?.split('-')[0] ?? 'en') as SupportedLocale;
  const dir = RTL_LOCALES.has(base) ? 'rtl' : 'ltr';
  document.documentElement.dir = dir;
  document.documentElement.lang = base;
}

export default i18n;
