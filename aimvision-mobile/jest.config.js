module.exports = {
  preset: 'jest-expo',
  setupFiles: ['<rootDir>/jest.setup.ts'],
  // Split the transform by extension so babel's parser only ever sees one
  // type system at a time. `babel-preset-expo` enables `@babel/preset-typescript`
  // with `allExtensions: true`, which forces the TS parser on `.js` files
  // too — and RN's vendor sources (`EventEmitter.js`, `error-guard.js`) ship
  // raw Flow syntax that the TS parser rejects. We bypass `babel.config.js`
  // here (`configFile: false`) and pick the right parser per extension.
  transform: {
    // Project source. TS parser handles `.ts/.tsx`.
    '\\.(ts|tsx)$': [
      'babel-jest',
      {
        configFile: false,
        babelrc: false,
        presets: [
          ['@babel/preset-env', { targets: { node: 'current' } }],
          '@babel/preset-typescript',
          ['@babel/preset-react', { runtime: 'automatic' }],
        ],
      },
    ],
    // Everything else (RN vendor + plain JS). Flow parser handles `.js/.jsx`.
    // `{ all: true }` strips Flow types from files without an `@flow` pragma
    // too, since not every RN vendor file declares one.
    '\\.(js|jsx|cjs|mjs)$': [
      'babel-jest',
      {
        configFile: false,
        babelrc: false,
        presets: [
          ['@babel/preset-env', { targets: { node: 'current' } }],
          ['@babel/preset-flow', { all: true }],
          ['@babel/preset-react', { runtime: 'automatic' }],
        ],
      },
    ],
  },
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
  testMatch: ['<rootDir>/src/**/__tests__/**/*.test.(ts|tsx)'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}', '!src/**/*.d.ts', '!src/**/__tests__/**'],
};
