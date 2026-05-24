/**
 * Statsig wrapper — currently a no-op stub.
 *
 * The previous integration via `statsig-react-native-expo` is incompatible
 * with React 19 (the SDK's peer dep is React ≤ 18). The app never actually
 * configured a STATSIG_CLIENT_KEY, so initialize() was always an early
 * return; useFlag(name, default) just resolves to the default. This stub
 * keeps the API surface so callers do not change, and `useFlag()` continues
 * to return the supplied default (e.g. `__DEV__` for the phone-capture flag).
 * Reinstate a real flag SDK when one ships with React-19 support.
 */

export interface StatsigUser {
  userID?: string;
  email?: string;
  custom?: Record<string, string | number | boolean>;
}

export async function initStatsig(_user: StatsigUser = {}): Promise<void> {
  return;
}

export function isInitialized(): boolean {
  return false;
}

export const Statsig = {
  checkGate(_name: string): boolean {
    return false;
  },
};
