/**
 * Typed wrapper around `import.meta.env`.
 * All AIMVISION-prefixed Vite envs MUST start with `VITE_AV_`.
 */

interface AvEnv {
  apiBaseUrl: string;
  sentryDsn: string | null;
  appEnv: 'development' | 'staging' | 'production' | 'test';
  buildVersion: string;
}

function readEnv<T extends string>(key: string, fallback: T): T {
  const v = (import.meta.env as Record<string, string | undefined>)[key];
  return (v ?? fallback) as T;
}

export const env: AvEnv = {
  apiBaseUrl: readEnv('VITE_AV_API_BASE_URL', 'http://localhost:8000'),
  sentryDsn: (import.meta.env.VITE_AV_SENTRY_DSN as string | undefined) ?? null,
  appEnv: readEnv<'development' | 'staging' | 'production' | 'test'>(
    'VITE_AV_APP_ENV',
    (import.meta.env.MODE as 'development' | 'production' | 'test') ?? 'development',
  ),
  buildVersion: readEnv('VITE_AV_BUILD_VERSION', '0.0.0-dev'),
};
