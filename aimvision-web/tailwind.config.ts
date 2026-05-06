import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tokens kept in sync with src/theme/tokens.ts (WCAG AA contrast pairs).
        brand: {
          DEFAULT: '#0f172a',
          fg: '#f8fafc',
          accent: '#2563eb',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f1f5f9',
          inverted: '#0f172a',
        },
        text: {
          DEFAULT: '#0f172a',
          muted: '#475569',
          inverted: '#f8fafc',
        },
        border: {
          DEFAULT: '#e2e8f0',
          strong: '#94a3b8',
        },
        focus: '#2563eb',
        danger: '#b91c1c',
        success: '#15803d',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        arabic: ['Cairo', 'Tajawal', 'system-ui', 'sans-serif'],
      },
      minHeight: {
        touch: '44px',
      },
      minWidth: {
        touch: '44px',
      },
    },
  },
  plugins: [],
};

export default config;
