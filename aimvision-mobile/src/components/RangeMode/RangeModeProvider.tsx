/**
 * Range Mode context. When ambient lux > 50,000 (UX review threshold), or when the
 * user has explicitly enabled Range Mode in Settings, rendering switches to
 * RangeModeTheme: maximum contrast, larger tap targets, no animations.
 *
 * Ambient-light sensor wiring is a Sprint 4 native-module deliverable; this provider
 * exposes the same public surface so consumers don't change.
 */
import React, { createContext, useContext, useMemo, useState } from 'react';
import { theme as defaultTheme } from '../../theme/tokens';
import { rangeModeTheme } from '../../theme/RangeModeTheme';
import type { Theme } from '../../theme/tokens';

export const RANGE_MODE_LUX_THRESHOLD = 50_000;

interface RangeModeContextValue {
  inRangeMode: boolean;
  theme: Theme;
  setManualOverride: (value: boolean | null) => void;
  setAmbientLux: (lux: number) => void;
}

const RangeModeContext = createContext<RangeModeContextValue | null>(null);

export function RangeModeProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [override, setOverride] = useState<boolean | null>(null);
  const [lux, setLux] = useState<number>(0);

  const inRangeMode = override ?? lux >= RANGE_MODE_LUX_THRESHOLD;

  const value = useMemo<RangeModeContextValue>(
    () => ({
      inRangeMode,
      theme: inRangeMode ? rangeModeTheme : defaultTheme,
      setManualOverride: setOverride,
      setAmbientLux: setLux,
    }),
    [inRangeMode],
  );

  return <RangeModeContext.Provider value={value}>{children}</RangeModeContext.Provider>;
}

export function useRangeMode(): RangeModeContextValue {
  const ctx = useContext(RangeModeContext);
  if (!ctx) {
    return {
      inRangeMode: false,
      theme: defaultTheme,
      setManualOverride: () => undefined,
      setAmbientLux: () => undefined,
    };
  }
  return ctx;
}
