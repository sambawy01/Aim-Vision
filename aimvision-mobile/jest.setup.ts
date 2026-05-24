/* eslint-disable @typescript-eslint/no-var-requires */
// RNTL 13's auto-extend used to be imported here, but it requires `expect`
// at import time which isn't available in `setupFiles`. The tests use the
// standard Jest matchers (toBe, toEqual, ...); any test wanting RNTL's
// custom matchers (toBeOnTheScreen, etc.) can import
// `@testing-library/react-native/extend-expect` in-test.

jest.mock('expo-localization', () => ({
  getLocales: jest.fn(() => [{ languageCode: 'en', regionCode: 'US', textDirection: 'ltr' }]),
  locale: 'en-US',
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));

jest.mock('expo-constants', () => ({
  expoConfig: {
    extra: {
      env: {
        API_BASE_URL: 'https://api.aimvision.test',
        SENTRY_DSN: '',
        STATSIG_CLIENT_KEY: '',
        OTEL_ENDPOINT: '',
      },
      locale: {
        supportsRTL: true,
        defaultLocale: 'en',
        supportedLocales: ['en', 'ar'],
      },
    },
  },
}));

jest.mock('expo-updates', () => ({
  reloadAsync: jest.fn(async () => undefined),
  isEnabled: false,
}));

jest.mock('@sentry/react-native', () => ({
  init: jest.fn(),
  addBreadcrumb: jest.fn(),
  captureException: jest.fn(),
  setUser: jest.fn(),
  withScope: jest.fn((cb: (scope: unknown) => void) => cb({ setTag: jest.fn() })),
}));

