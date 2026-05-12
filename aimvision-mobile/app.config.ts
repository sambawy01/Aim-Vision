import type { ConfigContext, ExpoConfig } from 'expo/config';

// Static config in `app.json` is read first by Expo and passed in as
// `config`. This file overlays the runtime-env fields from `process.env`
// so secrets stay out of source. EAS Build injects values via `eas.json`;
// local dev sets them in the shell (or via direnv / a .env loader).
//
// The four contract vars are documented in `.env.example`.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  // `config.name` and `config.slug` are typed optional in ConfigContext but
  // ExpoConfig requires them — they always come from app.json so just pass
  // through with a defensive default.
  name: config.name ?? 'AIMVISION',
  slug: config.slug ?? 'aimvision-mobile',
  extra: {
    ...config.extra,
    env: {
      API_BASE_URL: process.env.API_BASE_URL ?? 'https://api.aimvision.com',
      SENTRY_DSN: process.env.SENTRY_DSN ?? '',
      STATSIG_CLIENT_KEY: process.env.STATSIG_CLIENT_KEY ?? '',
      OTEL_ENDPOINT: process.env.OTEL_ENDPOINT ?? '',
    },
  },
});
