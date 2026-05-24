import { isInitialized, Statsig } from '../config/statsig';

/**
 * Returns a feature-flag value. Falls back to `defaultValue` when the flag
 * SDK is not initialized — which is the current state (see config/statsig.ts).
 */
export function useFlag(name: string, defaultValue = false): boolean {
  if (!isInitialized()) return defaultValue;
  try {
    return Statsig.checkGate(name);
  } catch {
    return defaultValue;
  }
}
