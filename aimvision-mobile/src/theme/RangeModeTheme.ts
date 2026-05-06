/**
 * High-contrast outdoor variant — Range Mode.
 * Activated when ambient light exceeds 50,000 lux (UX review threshold) or via Settings.
 * See docs/mobile-architecture.md §14 (Range Mode).
 */
import { spacing, radii } from './tokens';
import type { Theme } from './tokens';

const rangeColors = {
  bg: '#000000',
  surface: '#0A0A0A',
  surfaceElevated: '#161616',
  border: '#FFFFFF',
  textPrimary: '#FFFFFF',
  textSecondary: '#FFFFFF',
  textMuted: '#D8D8D8',
  accent: '#FFD400',
  accentPressed: '#E0B800',
  success: '#00FF85',
  warning: '#FFD400',
  danger: '#FF453A',
  white: '#FFFFFF',
  black: '#000000',
} as const;

const rangeTypography = {
  body: 20,
  bodySmall: 17,
  caption: 15,
  title: 26,
  display: 34,
  monoBody: 20,
} as const;

const rangeTapTargets = {
  minimum: 56,
  primary: 72,
} as const;

export const rangeModeTheme: Theme = {
  colors: rangeColors,
  spacing,
  radii,
  typography: rangeTypography,
  tapTargets: rangeTapTargets,
};
