import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AppStackParamList } from './types';
import { usePhoneCaptureEnabled } from '../config/flags';
import { HomeScreen } from '../screens/home/HomeScreen';
import { SettingsScreen } from '../screens/settings/SettingsScreen';
import { DataPrivacyScreen } from '../screens/settings/DataPrivacyScreen';
import { CapturePhoneScreen } from '../screens/capture/CapturePhoneScreen';

const Stack = createNativeStackNavigator<AppStackParamList>();

export function AppStack(): React.ReactElement {
  // ADR-0009: the dev-mode phone-capture screen is only registered when the
  // `capture.phone_backend_enabled` flag is on. Default off in production, so
  // a customer build can't resolve the route even via a deep link.
  const phoneCaptureEnabled = usePhoneCaptureEnabled();

  return (
    <Stack.Navigator initialRouteName="Home">
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Settings" component={SettingsScreen} />
      <Stack.Screen name="DataPrivacy" component={DataPrivacyScreen} />
      {phoneCaptureEnabled ? (
        <Stack.Screen name="CapturePhone" component={CapturePhoneScreen} />
      ) : null}
    </Stack.Navigator>
  );
}
