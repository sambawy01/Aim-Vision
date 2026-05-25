/**
 * Statsig client init — local-dev stub.
 *
 * The real `statsig-react-native-expo` SDK peers on React ≤18; once the
 * mobile RN modernization to React 19 lands (PR #92 follow-up), we
 * either switch to the rewritten Statsig RN SDK or keep this stub as
 * the offline default per docs/mobile-architecture.md §13.
 *
 * Public API matches the real one so call sites don't change.
 */

export interface StatsigUser {
  userID?: string;
  email?: string;
  custom?: Record<string, string | number | boolean>;
}

// Intentionally stays false. `useFlag` short-circuits when not
// initialized, so every flag falls back to its hard-coded `defaultValue`
// — which is what we want until a real Statsig SDK is wired back in.
// Earlier we set this to `true` after `initStatsig()`, which made
// `checkGate()` (the stubbed-to-`false` impl below) override every
// caller's default.
let initialized = false;

export async function initStatsig(_user: StatsigUser = {}): Promise<void> {
  // No-op stub.
}

export function isInitialized(): boolean {
  return initialized;
}

export const Statsig = {
  checkGate(_name: string): boolean {
    return false;
  },
  getConfig(_name: string): { get<T>(_key: string, fallback: T): T } {
    return { get: (_k, fallback) => fallback };
  },
  getExperiment(_name: string): { get<T>(_key: string, fallback: T): T } {
    return { get: (_k, fallback) => fallback };
  },
  shutdown(): void {
    initialized = false;
  },
} as const;
