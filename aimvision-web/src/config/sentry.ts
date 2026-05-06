import * as Sentry from '@sentry/react';
import { env } from './env';

let initialized = false;

export function initSentry(): void {
  if (initialized) return;
  initialized = true;

  if (!env.sentryDsn) {
    // No DSN configured (typical for local dev / tests); skip init silently.
    return;
  }

  Sentry.init({
    dsn: env.sentryDsn,
    environment: env.appEnv,
    release: env.buildVersion,
    tracesSampleRate: env.appEnv === 'production' ? 0.1 : 1.0,
    // PII off by default per docs/security/multi-tenant-isolation.md §6.
    sendDefaultPii: false,
  });
}
