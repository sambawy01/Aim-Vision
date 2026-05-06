module.exports = {
  root: true,
  // The `expo` preset already pulls in eslint-plugin-react, react-hooks, and
  // jsx-a11y. We add @typescript-eslint on top. Avoid the
  // react-native-a11y preset until we audit whether its rules align with
  // @typescript-eslint v8 (it transitively requires the removed
  // `@typescript-eslint/ban-types` rule definition).
  extends: ['expo', 'plugin:@typescript-eslint/recommended'],
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  env: {
    es2022: true,
    jest: true,
  },
  rules: {
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
  },
  ignorePatterns: [
    'node_modules/',
    'ios/',
    'android/',
    'babel.config.js',
    'metro.config.js',
    'jest.config.js',
    'jest.setup.ts',
    '.eslintrc.cjs',
    '.prettierrc.cjs',
  ],
};
