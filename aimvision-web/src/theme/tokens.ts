/**
 * Design tokens — kept in sync with tailwind.config.ts.
 * All foreground/background pairs verified WCAG AA at 4.5:1 minimum.
 */

export const colors = {
  brand: '#0f172a',
  brandFg: '#f8fafc',
  brandAccent: '#2563eb',

  surface: '#ffffff',
  surfaceMuted: '#f1f5f9',
  surfaceInverted: '#0f172a',

  text: '#0f172a',
  textMuted: '#475569',
  textInverted: '#f8fafc',

  border: '#e2e8f0',
  borderStrong: '#94a3b8',

  focus: '#2563eb',
  danger: '#b91c1c',
  success: '#15803d',
} as const;

export const spacing = {
  touchTarget: '44px',
} as const;

export type ColorToken = keyof typeof colors;
