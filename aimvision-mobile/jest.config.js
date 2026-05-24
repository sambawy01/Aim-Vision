module.exports = {
  preset: 'jest-expo',
  setupFiles: ['<rootDir>/jest.setup.ts'],
  // Trust jest-expo's default transform (babel-preset-expo). Before SDK 56 RN
  // vendor `.js` was raw Flow and needed a split-by-extension override here;
  // SDK 56 / RN 0.85 transitioned much of that vendor code to TS-in-`.js`
  // (e.g. `@react-native/jest-preset/jest/mock.js` uses `ref as string`), and
  // the override sent those files through the Flow parser which rejected the
  // `as` cast. preset-expo for SDK 56 picks the right parser per file.
  transformIgnorePatterns: [
    // Two patterns because pnpm resolves packages through a flat virtual
    // store at `node_modules/.pnpm/<pkg>@<ver>/node_modules/<pkg>/...`,
    // and a single regex with an optional `.pnpm/` prefix backtracks
    // (the optional group consumes zero chars and the lookahead then
    // tests against `.pnpm/...`, which is not in the allowlist, so the
    // file gets wrongly ignored). Two anchored patterns avoid that.
    // Match `node_modules/<pkg>` at the top level — exclude `.pnpm` itself.
    'node_modules/(?!\\.pnpm/)(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@sentry/.*|statsig-.*|@shopify/react-native-skia))',
    // Match the pnpm-nested layout: `node_modules/.pnpm/<pkg>@<ver>/node_modules/<pkg>`.
    'node_modules/\\.pnpm/[^/]+/node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@sentry/.*|statsig-.*|@shopify/react-native-skia))',
  ],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: [
    '<rootDir>/src/**/__tests__/**/*.test.(ts|tsx)',
    // Expo config plugins live outside src/ so they can be picked up by
    // `expo prebuild` from their canonical location. Their unit tests
    // run from `plugins/**/__tests__`.
    '<rootDir>/plugins/**/__tests__/**/*.test.(ts|tsx)',
  ],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    'plugins/**/*.{ts,tsx}',
    '!**/*.d.ts',
    '!**/__tests__/**',
  ],
};
