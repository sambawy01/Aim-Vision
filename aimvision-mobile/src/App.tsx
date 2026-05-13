/**
 * App root. Boots i18n + RTL, Sentry, Statsig, OTel placeholder, and rehydrates auth.
 * See docs/adr/0002-mobile-rn-new-architecture.md and docs/mobile-architecture.md.
 */
import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import { initI18n } from './config/i18n';
import { initSentry } from './config/sentry';
import { initStatsig } from './config/statsig';
import { initOtel } from './config/otel';
import { startTelemetrySubscribers, type TelemetryHandle } from './services/telemetry';
import { useAuthStore } from './state/authStore';
import { RangeModeProvider } from './components/RangeMode';
import { RootNavigator } from './navigation/RootNavigator';

export default function App(): React.ReactElement | null {
  const [ready, setReady] = useState(false);
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    let mounted = true;
    let telemetry: TelemetryHandle | null = null;
    (async () => {
      try {
        initSentry();
      } catch (err) {
        console.warn('initSentry failed; continuing', err);
      }
      try {
        telemetry = startTelemetrySubscribers();
      } catch (err) {
        console.warn('telemetry subscribers failed; continuing', err);
      }
      try {
        initOtel();
      } catch (err) {
        console.warn('initOtel failed; continuing', err);
      }
      try {
        await initI18n();
      } catch (err) {
        console.warn('initI18n failed; continuing with defaults', err);
      }
      // Auth hydrate + Statsig init failures must not gate the UI. The
      // app should render in a logged-out state if storage is unavailable
      // (e.g. web preview without expo-secure-store polyfill) or the
      // flag SDK is offline.
      const results = await Promise.allSettled([hydrate(), initStatsig()]);
      for (const r of results) {
        if (r.status === 'rejected') {
          console.warn('non-fatal init rejection', r.reason);
        }
      }
      if (mounted) setReady(true);
    })();
    return () => {
      mounted = false;
      telemetry?.dispose();
    };
  }, [hydrate]);

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <RangeModeProvider>
          <StatusBar style="light" />
          <NavigationContainer>
            <RootNavigator />
          </NavigationContainer>
        </RangeModeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
