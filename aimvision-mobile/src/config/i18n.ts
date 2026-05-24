/**
 * i18next setup with EN + AR + RTL bootstrap.
 * See docs/mobile-architecture.md §15 (i18n / RTL).
 */
// Hermes (RN's JS engine) ships only partial Intl support, so
// `Intl.PluralRules` is missing. i18next's pluralResolver detects this and
// falls back to compatibilityJSON v3 with a noisy red LogBox overlay. The
// polyfill MUST be imported before i18next/initReactI18next is touched.
import 'intl-pluralrules';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { I18nManager } from 'react-native';
import * as Localization from 'expo-localization';
import * as Updates from 'expo-updates';

import en from '../locales/en/common.json';
import ar from '../locales/ar/common.json';

const SUPPORTED = ['en', 'ar'] as const;
export type SupportedLocale = (typeof SUPPORTED)[number];

function detectLocale(): SupportedLocale {
  const locales = Localization.getLocales();
  const first = locales?.[0]?.languageCode ?? 'en';
  return (SUPPORTED as readonly string[]).includes(first) ? (first as SupportedLocale) : 'en';
}

let didReloadForRTL = false;

export async function initI18n(): Promise<void> {
  const lng = detectLocale();
  const isRTLLocale = lng === 'ar';

  await i18n.use(initReactI18next).init({
    resources: {
      en: { common: en },
      ar: { common: ar },
    },
    lng,
    fallbackLng: 'en',
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    returnNull: false,
    compatibilityJSON: 'v4',
  });

  if (isRTLLocale && !I18nManager.isRTL && !didReloadForRTL) {
    didReloadForRTL = true;
    I18nManager.allowRTL(true);
    I18nManager.forceRTL(true);
    if (!__DEV__) {
      try {
        await Updates.reloadAsync();
      } catch {
        // Updates not available in dev / simulator — direction will apply on next cold start.
      }
    }
  } else if (!isRTLLocale && I18nManager.isRTL && !didReloadForRTL) {
    didReloadForRTL = true;
    I18nManager.forceRTL(false);
    if (!__DEV__) {
      try {
        await Updates.reloadAsync();
      } catch {
        // ignore
      }
    }
  }
}

export async function setLocale(locale: SupportedLocale): Promise<void> {
  await i18n.changeLanguage(locale);
  const wantsRTL = locale === 'ar';
  if (wantsRTL !== I18nManager.isRTL) {
    I18nManager.allowRTL(wantsRTL);
    I18nManager.forceRTL(wantsRTL);
  }
}

export default i18n;
