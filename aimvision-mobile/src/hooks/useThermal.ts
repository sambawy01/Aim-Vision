/**
 * Thermal state hook. iOS exposes ProcessInfo.thermalState; Android exposes
 * PowerManager.currentThermalStatus. Both surface through a Sprint 7 native module
 * (per docs/mobile-architecture.md §10). This hook returns a normalized enum.
 */
import { useEffect, useState } from 'react';

export type ThermalState = 'nominal' | 'fair' | 'serious' | 'critical' | 'shutdown';

export function useThermal(): ThermalState {
  const [state, setState] = useState<ThermalState>('nominal');

  useEffect(() => {
    // Native bridge wired in Sprint 7 (uses `setState`). Until then: 'nominal'.
    void setState;
    return () => undefined;
  }, []);

  return state;
}
