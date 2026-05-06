/**
 * Sentry RN init with PII scrubbing.
 * See docs/mobile-architecture.md §13 (crash + performance) and §11 (mobile hardening).
 */
import * as Sentry from '@sentry/react-native';
import { env } from './env';

const PII_KEYS = new Set([
  'email',
  'first_name',
  'last_name',
  'name',
  'full_name',
  'phone',
  'parent_email',
  'parent_name',
]);

const ATHLETE_ID_KEYS = new Set(['athlete_id', 'child_id', 'parent_id']);

function djb2(input: string): string {
  let hash = 5381;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 33) ^ input.charCodeAt(i);
  }
  return `h_${(hash >>> 0).toString(16)}`;
}

function scrub(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (Array.isArray(value)) return value.map(scrub);
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (PII_KEYS.has(k)) {
        out[k] = '[redacted]';
      } else if (ATHLETE_ID_KEYS.has(k) && typeof v === 'string') {
        out[k] = djb2(v);
      } else {
        out[k] = scrub(v);
      }
    }
    return out;
  }
  return value;
}

export function initSentry(): void {
  if (!env.sentryDsn) {
    return;
  }
  Sentry.init({
    dsn: env.sentryDsn,
    tracesSampleRate: 0.2,
    attachStacktrace: true,
    enableNative: true,
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.user) {
        event.user = scrub(event.user) as typeof event.user;
      }
      if (event.extra) {
        event.extra = scrub(event.extra) as typeof event.extra;
      }
      if (event.contexts) {
        event.contexts = scrub(event.contexts) as typeof event.contexts;
      }
      return event;
    },
  });
}

export { Sentry };
