/**
 * Typed environment access via Expo Constants.
 * See docs/mobile-architecture.md §13 for OTA + Sentry + Statsig wiring.
 */
import Constants from 'expo-constants';

export interface AppEnv {
  apiBaseUrl: string;
  sentryDsn: string;
  statsigClientKey: string;
  otelEndpoint: string;
}

interface ExtraConfig {
  env?: Partial<
    AppEnv & {
      API_BASE_URL: string;
      SENTRY_DSN: string;
      STATSIG_CLIENT_KEY: string;
      OTEL_ENDPOINT: string;
    }
  >;
  locale?: {
    supportsRTL: boolean;
    defaultLocale: string;
    supportedLocales: string[];
  };
  eas?: { projectId?: string };
}

const extra = (Constants.expoConfig?.extra ?? {}) as ExtraConfig;
const raw = extra.env ?? {};

export const env: AppEnv = {
  apiBaseUrl: raw.API_BASE_URL ?? 'https://api.aimvision.com',
  sentryDsn: raw.SENTRY_DSN ?? '',
  statsigClientKey: raw.STATSIG_CLIENT_KEY ?? '',
  otelEndpoint: raw.OTEL_ENDPOINT ?? '',
};

export const localeConfig = extra.locale ?? {
  supportsRTL: true,
  defaultLocale: 'en',
  supportedLocales: ['en', 'ar'],
};

export const easProjectId: string | undefined = extra.eas?.projectId;
