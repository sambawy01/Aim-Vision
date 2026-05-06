/**
 * Design tokens. Color pairs verified at WCAG AA (4.5:1 body, 7:1 primary).
 * See docs/mobile-architecture.md §14.
 */
export const colors = {
  bg: '#0B0F14',
  surface: '#121821',
  surfaceElevated: '#1B232E',
  border: '#2A3340',
  textPrimary: '#F4F6F8',
  textSecondary: '#B7C0CC',
  textMuted: '#7A8492',
  accent: '#3DA9FC',
  accentPressed: '#2C8AD9',
  success: '#3DDC97',
  warning: '#F4B400',
  danger: '#E5484D',
  white: '#FFFFFF',
  black: '#000000',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radii = {
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
} as const;

export const typography = {
  body: 17,
  bodySmall: 15,
  caption: 13,
  title: 22,
  display: 28,
  monoBody: 16,
} as const;

export const minHitSlop = { top: 8, bottom: 8, left: 8, right: 8 } as const;

export const tapTargets = {
  minimum: 44,
  primary: 56,
} as const;

// Theme is a structural shape, not a literal-narrowed shape, so variants
// (e.g. Range Mode) can override values without `as const` clashes.
export type Colors = { readonly [K in keyof typeof colors]: string };
export type Spacing = { readonly [K in keyof typeof spacing]: number };
export type Radii = { readonly [K in keyof typeof radii]: number };
export type Typography = { readonly [K in keyof typeof typography]: number };
export type TapTargets = { readonly [K in keyof typeof tapTargets]: number };

export type Theme = {
  colors: Colors;
  spacing: Spacing;
  radii: Radii;
  typography: Typography;
  tapTargets: TapTargets;
};

export const theme: Theme = { colors, spacing, radii, typography, tapTargets };
