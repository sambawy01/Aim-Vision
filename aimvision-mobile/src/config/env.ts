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
  /** `development`, `staging`, or `production`. Drives env-conditional defaults. */
  appEnv: 'development' | 'staging' | 'production';
}

interface ExtraConfig {
  env?: Partial<
    AppEnv & {
      API_BASE_URL: string;
      SENTRY_DSN: string;
      STATSIG_CLIENT_KEY: string;
      OTEL_ENDPOINT: string;
      APP_ENV: 'development' | 'staging' | 'production';
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
  appEnv: raw.APP_ENV ?? (__DEV__ ? 'development' : 'production'),
};

export const localeConfig = extra.locale ?? {
  supportsRTL: true,
  defaultLocale: 'en',
  supportedLocales: ['en', 'ar'],
};

export const easProjectId: string | undefined = extra.eas?.projectId;
