/* eslint-disable @typescript-eslint/no-var-requires */
import '@testing-library/react-native';

jest.mock('expo-localization', () => ({
  getLocales: jest.fn(() => [
    { languageCode: 'en', regionCode: 'US', textDirection: 'ltr' },
  ]),
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

jest.mock('statsig-react-native-expo', () => ({
  Statsig: {
    initialize: jest.fn(async () => undefined),
    checkGate: jest.fn(() => false),
    getConfig: jest.fn(() => ({ get: jest.fn() })),
  },
  StatsigProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('react-native-reanimated', () =>
  require('react-native-reanimated/mock'),
);

jest.mock('react-native-gesture-handler', () => {
  const View = require('react-native').View;
  return {
    GestureHandlerRootView: View,
    Swipeable: View,
    DrawerLayout: View,
    State: {},
    ScrollView: View,
    Slider: View,
    Switch: View,
    TextInput: View,
    ToolbarAndroid: View,
    ViewPagerAndroid: View,
    DrawerLayoutAndroid: View,
    WebView: View,
    NativeViewGestureHandler: View,
    TapGestureHandler: View,
    FlingGestureHandler: View,
    ForceTouchGestureHandler: View,
    LongPressGestureHandler: View,
    PanGestureHandler: View,
    PinchGestureHandler: View,
    RotationGestureHandler: View,
    Directions: {},
  };
});
