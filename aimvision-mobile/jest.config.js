module.exports = {
  preset: 'jest-expo',
  setupFiles: ['<rootDir>/jest.setup.ts'],
  transformIgnorePatterns: [
    // The optional `\.pnpm/<pkg>@<ver>/node_modules/` prefix is required so
    // packages resolved through pnpm's flat virtual store (e.g.
    // `node_modules/.pnpm/@react-native+js-polyfills@0.76.3/node_modules/@react-native/js-polyfills/...`)
    // still get transformed.
    'node_modules/(?:\\.pnpm/[^/]+/node_modules/)?(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@sentry/.*|statsig-.*|@shopify/react-native-skia))',
  ],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: ['<rootDir>/src/**/__tests__/**/*.test.(ts|tsx)'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}', '!src/**/*.d.ts', '!src/**/__tests__/**'],
};
