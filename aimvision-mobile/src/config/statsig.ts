/**
 * Statsig client init.
 * See docs/mobile-architecture.md §13 — feature flags + experiments + offline defaults.
 */
import { Statsig } from 'statsig-react-native-expo';
import { env } from './env';

export interface StatsigUser {
  userID?: string;
  email?: string;
  custom?: Record<string, string | number | boolean>;
}

let initialized = false;

export async function initStatsig(user: StatsigUser = {}): Promise<void> {
  if (!env.statsigClientKey || initialized) return;
  await Statsig.initialize(env.statsigClientKey, user, {
    environment: { tier: __DEV__ ? 'development' : 'production' },
  });
  initialized = true;
}

export function isInitialized(): boolean {
  return initialized;
}

export { Statsig };
