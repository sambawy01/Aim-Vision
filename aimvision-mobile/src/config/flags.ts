import { useFlag } from '../hooks/useFlag';

/**
 * Statsig gate names. The gate name is the contract with Statsig — keep it
 * stable across versions or migrate explicitly.
 */

/** ADR-0009 dev-mode phone-capture backend. */
export const FLAG_PHONE_CAPTURE = 'capture.phone_backend_enabled';

/**
 * Whether the ADR-0009 dev-mode phone-capture entry point is available.
 *
 * Default is `__DEV__`: ON in development builds so the team can capture real
 * range footage without configuring Statsig, and OFF in production builds so a
 * shipped customer build can never reach the dev capture screen. A production
 * Statsig gate can still flip it on for a specific internal build/user. This
 * is the in-code enforcement of the ADR-0009 constraint
 * ("the dev-mode entry point cannot be hit by a customer").
 *
 * Cite docs/adr/0009-phone-capture-dev-backend.md.
 */
export function usePhoneCaptureEnabled(): boolean {
  return useFlag(FLAG_PHONE_CAPTURE, __DEV__);
}
